#! /usr/bin/python3
#
# SPDX-License-Identifier: MIT
# Copyright (c) 2022 MBition GmbH
#
# Implementation of the "lazy" somersault ECU

import odxtools
from odxtools.odxtypes import bytefield_to_bytearray
import odxtools.uds as uds
import aioisotp
import somersaultecu
import asyncio
import time
import argparse
import logging
import random

tester_logger = logging.getLogger('somersault_lazy_tester')
ecu_logger = logging.getLogger('somersault_lazy_ecu')

somersault_lazy_diag_layer = somersaultecu.database.ecus.somersault_lazy

class SomersaultLazyServer(asyncio.Protocol):
    def __init__(self):
        self._diag_session_open = False
        self._data_receive_event = asyncio.Event()
        self.task = asyncio.create_task(self._run())

        self.dizziness_level = 0
        self.max_dizziness_level = 10

        ##############
        # extract the tester present parameters from the ECU's
        # communication parameters.
        #
        # TODO: move this into the DiagLayer analogous to
        # get_receive_id() plus deal with more parameters.
        ##############

        # the timeout on inactivity [s]
        cps = list(filter(lambda x: x.id_ref == "ISO_14230_3.CP_TesterPresentTime",
                          somersault_lazy_diag_layer.communication_parameters))
        if len(cps):
            assert len(cps) == 1
            self._idle_timeout = int(cps[0].value) / 1e6
        else:
            self._idle_timeout = 3.0 # default specified by the standard

        # we send a response to tester present messages. make sure
        # that this is specified
        cps = list(filter(lambda x: x.id_ref == "ISO_15765_3.CP_TesterPresentReqRsp",
                          somersault_lazy_diag_layer.communication_parameters))
        assert len(cps) == 1
        assert cps[0].value == "Response expected" or cps[0].value == "1"

    def connection_made(self, transport):
        self.transport = transport
        ecu_logger.debug(f"connection made")

    def connection_lost(self, exc):
        ecu_logger.debug(f"connection lost")

    def data_received(self, data):
        # to whom it may concern: we have received some data. This is
        # used to make sure that we do not run into the "tester
        # present" timeout spuriously
        self._data_receive_event.set()

        ecu_logger.debug(f"data received: 0x{data.hex()}")

        # decode the data
        try:
            messages = somersault_lazy_diag_layer.decode(data)

            # do the actual work which we were asked to do. we assume
            # that requests can always be uniquely decoded
            assert len(messages) == 1
            self.handle_request(messages[0])
        except odxtools.exceptions.DecodeError as e:
            ecu_logger.warning(f"Could not decode request: {e}")
            return

    def handle_request(self, message):
        service = message.service

        ecu_logger.info(f"received message: {service.short_name}")

        # keep alive message.
        if service.short_name == "tester_present":
            # send a positive response if have an active diagnostic
            # session, and a negative one if we don't.
            if self._diag_session_open:
                response_payload = service.positive_responses[0].encode(coded_request = message.coded_message)
            else:
                response_payload = service.negative_responses[0].encode(coded_request = message.coded_message)

            self.transport.write(response_payload)
            return

        if service.short_name == "session_start":
            if not self._diag_session_open:
                response_payload = service.positive_responses[0].encode(coded_request = message.coded_message,
                                                                        can_do_backward_flips = "false")
            else:
                response_payload = service.negative_responses[0].encode(coded_request = message.coded_message)

            self._diag_session_open = True
            self.transport.write(response_payload)
            return

        # from here on, a diagnostic session must be started or else
        # we will send a generic "ServiceNotSupportedInActiveSession"
        # UDS response
        if not self._diag_session_open:
            rq_id = 0
            if message.coded_message:
                rq_id = message.coded_message[0]

            # send a "service not supported in active session" UDS
            # response.
            self.transport.write(bytes([0x7f, rq_id, 0x7f]))
            return

        # stop the diagnostic session
        if service.short_name == "session_stop":
            if self._diag_session_open:
                response_payload = service.positive_responses[0].encode(coded_request = message.coded_message)
            else:
                response_payload = service.negative_responses[0].encode(coded_request = message.coded_message)

            self._diag_session_open = False
            self.transport.write(response_payload)
            return

        if service.short_name == "do_forward_flips":
            self.handle_forward_flip_request(message)
            return

    def handle_forward_flip_request(self, message):
        service = message.service
        # TODO: the need for .param_dict is quite ugly IMO,
        # i.e. provide a __getitem__() method for the Message class() (?)
        soberness_check = message.param_dict["forward_soberness_check"]
        num_flips = message.param_dict["num_flips"]

        if soberness_check != 0x12:
            response = next(filter(lambda x: x.short_name == "flips_not_done",
                                   service.negative_responses))
            response_data = response.encode(coded_request = message.coded_message,
                                            reason =  0, # -> not sober
                                            flips_successfully_done = 0)
            self.transport.write(response_data)
            return

        # we cannot do all flips because we are too dizzy
        if self.dizziness_level + num_flips > self.max_dizziness_level:

            response = next(filter(lambda x: x.short_name == "flips_not_done",
                                   service.negative_responses))
            response_data = response.encode(coded_request = message.coded_message,
                                            reason =  1, # -> too dizzy
                                            flips_successfully_done = self.max_dizziness_level - self.dizziness_level)
            self.transport.write(response_data)
            self.dizziness_level = self.max_dizziness_level
            return

        # do the flips, but be aware that 1% of our attempts fail
        # because we stumble
        for i in range(0, num_flips):
            if random.randrange(0, 10000) < 100:
                response = next(filter(lambda x: x.short_name == "flips_not_done",
                                       service.negative_responses))
                response_data = response.encode(coded_request = message.coded_message,
                                                reason =  2, # -> stumbled
                                                flips_successfully_done = i)
                self.transport.write(response_data)
                return

            self.dizziness_level += 1

        response = next(filter(lambda x: x.short_name == "grudging_forward",
                               service.positive_responses))
        response_data = response.encode(coded_request = message.coded_message)
        self.transport.write(response_data)

    def close_diag_session(self):
        if not self._diag_session_open:
            return

        self._diag_session_open = False

        # clean up data associated with the diagnostic session

    async def _run(self):
        ecu_logger.info("running diagnostic server")

        # task to close the diagnostic session if the tester has not
        # been seen for longer than the timeout specified by the ECU.
        while True:
            # sleep until we either hit our timeout or we've received
            # some data from the tester
            try:
                await asyncio.wait_for(self._data_receive_event.wait(),
                                       self._idle_timeout*1.05)
            except asyncio.exceptions.TimeoutError:
                # we ran into the idle timeout. Close the diagnostic
                # session if it is open. note that this also happens if
                # there is no active diagnostic session
                self.close_diag_session()
                continue
            except asyncio.exceptions.CancelledError:
                return

            if self._data_receive_event.is_set():
                # we have received some data
                self._data_receive_event.clear()
                continue

async def tester_await_response(isotp_reader, raw_message, timeout = 0.5):
    # await the answer from the server (be aware that the maximum
    # length of ISO-TP telegrams over the CAN bus is 4095 bytes)
    raw_response = await asyncio.wait_for(isotp_reader.read(4095), timeout)

    tester_logger.debug(f"received response")

    try:
        replies = somersault_lazy_diag_layer.decode_response(raw_response, raw_message)
        assert len(replies) == 1 # replies must always be uniquely decodable

        if replies[0].structure.response_type == "POS-RESPONSE":
            rtype = "positive"
        elif replies[0].structure.response_type == "NEG-RESPONSE":
            rtype = "negative"
        else:
            rtype = "unknown"

        tester_logger.debug(f"received {rtype} response")

        return replies[0]

    except odxtools.exceptions.DecodeError as e:
        if len(raw_response) >= 3:
            sid = raw_response[0]
            rq_sid = raw_response[1]
            error_id = raw_response[2]

            if sid == uds.NegativeResponseId:
                try:
                    rq_name = somersaultecu.SID(rq_sid).name
                except ValueError:
                    rq_name = f"0x{rq_sid:x}"
                error_name = uds.NegativeResponseCodes(error_id).name

                tester_logger.debug(f"Received negative response by service {rq_name}: {error_name}")
                return raw_response

        tester_logger.debug(f"Could not decode response: {e}")
        return raw_response

async def tester_main(network):
    tester_logger.info("running diagnostic tester")

    # receive and transmit IDs are flipped from the tester's perspective
    reader, writer = await network.open_connection(
        rxid=somersault_lazy_diag_layer.get_send_id(),
        txid=somersault_lazy_diag_layer.get_receive_id(),
    )

    # try to to do a single forward flip without having an active session (ought to fail)
    tester_logger.debug(f"attempting a sessionless forward flip")
    raw_message = somersault_lazy_diag_layer.services.do_forward_flips(forward_soberness_check=0x12,
                                                                       num_flips=1)
    writer.write(raw_message)
    await tester_await_response(reader, raw_message)

    # send "start session"
    tester_logger.debug(f"starting diagnostic session")
    raw_message = somersault_lazy_diag_layer.services.session_start()
    writer.write(raw_message)
    await tester_await_response(reader, raw_message)

    # attempt to do a single forward flip
    tester_logger.debug(f"attempting a forward flip")
    raw_message = somersault_lazy_diag_layer.services.do_forward_flips(forward_soberness_check=0x12,
                                                                       num_flips=1)
    writer.write(raw_message)
    await tester_await_response(reader, raw_message)

    # attempt to do a single forward flip but fail the soberness check
    tester_logger.debug(f"attempting a forward flip")
    raw_message = somersault_lazy_diag_layer.services.do_forward_flips(forward_soberness_check=0x23,
                                                                       num_flips=1)
    writer.write(raw_message)
    await tester_await_response(reader, raw_message)

    # attempt to do three forward flips
    tester_logger.debug(f"attempting three forward flip")
    raw_message = somersault_lazy_diag_layer.services.do_forward_flips(forward_soberness_check=0x12,
                                                                       num_flips=3)
    writer.write(raw_message)
    await tester_await_response(reader, raw_message)

    # attempt to do 50 forward flips (should always fail because of dizzyness)
    tester_logger.debug(f"attempting 50 forward flip")
    raw_message = somersault_lazy_diag_layer.services.do_forward_flips(forward_soberness_check=0x12,
                                                                       num_flips=50)
    writer.write(raw_message)
    await tester_await_response(reader, raw_message)

    tester_logger.debug(f"Finished")

async def main(args):
    if args.channel is not None:
        network = aioisotp.ISOTPNetwork(args.channel,
                                        interface='socketcan',
                                        receive_own_messages=True)
    else:
        network = aioisotp.ISOTPNetwork(interface='virtual',
                                        receive_own_messages=True)
    with network.open():
        # TODO: handle ISO-TP communication parameters (block size,
        # timings, ...) specified by the Somersault ECU
        server_task = None
        if args.mode in ["server", "unittest"]:
            # A server that uses a protocol
            transport, protocol = await network.create_connection(
                SomersaultLazyServer,
                rxid=somersault_lazy_diag_layer.get_receive_id(),
                txid=somersault_lazy_diag_layer.get_send_id(),
            )
            server_task = protocol.task

        tester_task = None
        if args.mode in ["tester", "unittest"]:
            tester_task = asyncio.create_task(tester_main(network))

        if args.mode == "server":
            await server_task
        elif args.mode == "tester":
            await tester_task
        else:
            logging.basicConfig(level=logging.DEBUG)
            logging.getLogger("odxtools").setLevel(logging.WARNING)
            logging.getLogger("aiosiotp").setLevel(logging.WARNING)
            logging.getLogger("aioisotp.network").setLevel(logging.WARNING)
            logging.getLogger("aioisotp.transports.userspace").setLevel(logging.WARNING)

            # run both tasks in parallel
            done, pending = await asyncio.wait([tester_task, server_task],
                                               return_when=asyncio.FIRST_COMPLETED)

            if tester_task in pending:
                tester_logger.error("The tester task did not terminate. This "
                                    "should *never* happen!")
                tester_task.cancel()

            if server_task not in pending:
                ecu_logger.error("The server task terminated. This "
                                 "should *never* happen!")
            else:
                # since only the tester terminates regularly, we need
                # to stop the task for the ECU here to avoid
                # complaints from asyncio...
                server_task.cancel()

parser = argparse.ArgumentParser(description="Provides an implementation for the 'lazy' variant of the somersault ECU")

parser.add_argument("--channel", "-c", default=None, help="CAN interface name to be used (required for tester or server modes)")
parser.add_argument("--mode", "-m", default="unittest", required=False, help="Specify whether to start the ECU side ('server'), the tester side ('tester') or both ('unittest')")

args = parser.parse_args() # deals with the help message handling

loop = asyncio.get_event_loop()
loop.run_until_complete(main(args))

