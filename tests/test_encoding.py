# SPDX-License-Identifier: MIT
import unittest

from odxtools.compumethods.limit import IntervalType, Limit
from odxtools.compumethods.linearcompumethod import LinearCompuMethod
from odxtools.dataobjectproperty import DataObjectProperty
from odxtools.exceptions import EncodeError
from odxtools.odxlink import OdxDocFragment, OdxLinkDatabase, OdxLinkId, OdxLinkRef
from odxtools.odxtypes import DataType
from odxtools.parameters.codedconstparameter import CodedConstParameter
from odxtools.parameters.nrcconstparameter import NrcConstParameter
from odxtools.parameters.valueparameter import ValueParameter
from odxtools.physicaltype import PhysicalType
from odxtools.request import Request
from odxtools.response import Response
from odxtools.standardlengthtype import StandardLengthType

doc_frags = [OdxDocFragment("UnitTest", "WinneThePoh")]


class TestEncodeRequest(unittest.TestCase):

    def test_encode_coded_const_infer_order(self):
        diag_coded_type = StandardLengthType(
            base_data_type=DataType.A_UINT32,
            base_type_encoding=None,
            bit_length=8,
            bit_mask=None,
            is_highlow_byte_order_raw=None,
            is_condensed_raw=None,
        )
        param1 = CodedConstParameter(
            short_name="coded_const_parameter",
            long_name=None,
            description=None,
            semantic=None,
            diag_coded_type=diag_coded_type,
            coded_value=0x7D,
            byte_position=0,
            bit_position=None,
            sdgs=[],
        )
        param2 = CodedConstParameter(
            short_name="coded_const_parameter",
            long_name=None,
            description=None,
            semantic=None,
            diag_coded_type=diag_coded_type,
            coded_value=0xAB,
            byte_position=None,
            bit_position=None,
            sdgs=[],
        )
        req = Request(
            odx_id=OdxLinkId("request_id", doc_frags),
            short_name="request_sn",
            long_name=None,
            description=None,
            sdgs=[],
            is_visible_raw=None,
            parameters=[param1, param2],
            byte_size=None,
        )
        self.assertEqual(req.encode(), bytearray([0x7D, 0xAB]))

    def test_encode_coded_const_reorder(self):
        diag_coded_type = StandardLengthType(
            base_data_type=DataType.A_UINT32,
            base_type_encoding=None,
            bit_length=8,
            bit_mask=None,
            is_highlow_byte_order_raw=None,
            is_condensed_raw=None,
        )
        param1 = CodedConstParameter(
            short_name="param1",
            long_name=None,
            description=None,
            semantic=None,
            diag_coded_type=diag_coded_type,
            coded_value=0x34,
            byte_position=1,
            bit_position=None,
            sdgs=[],
        )
        param2 = CodedConstParameter(
            short_name="param2",
            long_name=None,
            description=None,
            semantic=None,
            diag_coded_type=diag_coded_type,
            coded_value=0x12,
            byte_position=0,
            bit_position=None,
            sdgs=[],
        )
        req = Request(
            odx_id=OdxLinkId("request_id", doc_frags),
            short_name="request_sn",
            long_name=None,
            description=None,
            sdgs=[],
            is_visible_raw=None,
            parameters=[param1, param2],
            byte_size=None,
        )
        self.assertEqual(req.encode(), bytearray([0x12, 0x34]))

    def test_encode_linear(self):
        odxlinks = OdxLinkDatabase()
        diag_coded_type = StandardLengthType(
            base_data_type=DataType.A_UINT32,
            base_type_encoding=None,
            bit_length=8,
            bit_mask=None,
            is_highlow_byte_order_raw=None,
            is_condensed_raw=None,
        )
        # This CompuMethod represents the linear function: decode(x) = 2*x + 8 and encode(x) = (x-8)/2
        compu_method = LinearCompuMethod(
            offset=8,
            factor=2,
            denominator=1,
            internal_type=DataType.A_UINT32,
            physical_type=DataType.A_UINT32,
            internal_lower_limit=Limit(0, IntervalType.INFINITE),
            internal_upper_limit=Limit(0, IntervalType.INFINITE),
        )
        dop = DataObjectProperty(
            odx_id=OdxLinkId("dop.id", doc_frags),
            short_name="dop_sn",
            long_name="example dop",
            description=None,
            is_visible_raw=None,
            diag_coded_type=diag_coded_type,
            physical_type=PhysicalType(DataType.A_UINT32, display_radix=None, precision=None),
            compu_method=compu_method,
            unit_ref=None,
            sdgs=[],
        )
        odxlinks.update({dop.odx_id: dop})
        param1 = ValueParameter(
            short_name="value_parameter",
            long_name=None,
            description=None,
            semantic=None,
            dop_ref=OdxLinkRef.from_id(dop.odx_id),
            dop_snref=None,
            physical_default_value_raw=None,
            byte_position=None,
            bit_position=None,
            sdgs=[],
        )
        req = Request(
            odx_id=OdxLinkId("request.id", doc_frags),
            short_name="request_sn",
            long_name=None,
            description=None,
            sdgs=[],
            is_visible_raw=None,
            parameters=[param1],
            byte_size=None,
        )

        param1._resolve_odxlinks(odxlinks)
        param1._resolve_snrefs(None)

        # Missing mandatory parameter.
        with self.assertRaises(TypeError):
            req.encode()

        self.assertEqual(
            req.encode(value_parameter=14),
            bytearray([0x3])  # encode(14) = (14-8)/2 = 3
        )

    def test_encode_nrc_const(self):
        diag_coded_type = StandardLengthType(
            base_data_type=DataType.A_UINT32,
            base_type_encoding=None,
            bit_length=8,
            bit_mask=None,
            is_highlow_byte_order_raw=None,
            is_condensed_raw=None,
        )
        param1 = CodedConstParameter(
            short_name="param1",
            long_name=None,
            description=None,
            semantic=None,
            diag_coded_type=diag_coded_type,
            coded_value=0x12,
            byte_position=0,
            bit_position=None,
            sdgs=[],
        )
        param2 = NrcConstParameter(
            short_name="param2",
            long_name=None,
            description=None,
            semantic=None,
            diag_coded_type=diag_coded_type,
            coded_values=[0x34, 0xAB],
            byte_position=1,
            bit_position=None,
            sdgs=[],
        )
        resp = Response(
            odx_id=OdxLinkId("response_id", doc_frags),
            short_name="response_sn",
            long_name=None,
            description=None,
            sdgs=[],
            is_visible_raw=None,
            response_type="POS-RESPONSE",
            parameters=[param1, param2],
            byte_size=None,
        )
        self.assertEqual(resp.encode(), bytearray([0x12, 0x34]))
        self.assertEqual(resp.encode(param2=0xAB), bytearray([0x12, 0xAB]))
        self.assertRaises(EncodeError, resp.encode, param2=0xEF)

    def test_encode_overlapping(self):
        uint24 = StandardLengthType(
            base_data_type=DataType.A_UINT32,
            base_type_encoding=None,
            bit_length=24,
            bit_mask=None,
            is_highlow_byte_order_raw=None,
            is_condensed_raw=None,
        )
        uint8 = StandardLengthType(
            base_data_type=DataType.A_UINT32,
            base_type_encoding=None,
            bit_length=8,
            bit_mask=None,
            is_highlow_byte_order_raw=None,
            is_condensed_raw=None,
        )
        param1 = CodedConstParameter(
            short_name="code",
            long_name=None,
            description=None,
            semantic=None,
            diag_coded_type=uint24,
            coded_value=0x123456,
            byte_position=0,
            bit_position=None,
            sdgs=[],
        )
        param2 = CodedConstParameter(
            short_name="part1",
            long_name=None,
            description=None,
            semantic=None,
            diag_coded_type=uint8,
            coded_value=0x23,
            byte_position=0,
            bit_position=4,
            sdgs=[],
        )
        param3 = CodedConstParameter(
            short_name="part2",
            long_name=None,
            description=None,
            semantic=None,
            diag_coded_type=uint8,
            coded_value=0x45,
            byte_position=1,
            bit_position=4,
            sdgs=[],
        )
        req = Request(
            odx_id=OdxLinkId("request_id", doc_frags),
            short_name="request_sn",
            long_name=None,
            description=None,
            sdgs=[],
            is_visible_raw=None,
            parameters=[param1, param2, param3],
            byte_size=None,
        )
        self.assertEqual(req.encode(), bytearray([0x12, 0x34, 0x56]))
        self.assertEqual(req.bit_length, 24)

    def test_issue_70(self):
        # see https://github.com/mercedes-benz/odxtools/issues/70
        # make sure overlapping params don't cause this function to go crazy
        unit_kwargs = dict(
            base_data_type=DataType.A_UINT32,
            base_type_encoding=None,
            is_highlow_byte_order_raw=None,
            bit_mask=None,
            is_condensed_raw=None,
        )
        uint2 = StandardLengthType(bit_length=2, **unit_kwargs)
        uint1 = StandardLengthType(bit_length=1, **unit_kwargs)
        param_kwargs = dict(
            long_name=None,
            description=None,
            byte_position=None,
            semantic=None,
            sdgs=[],
            coded_value=0,
        )
        params = [
            CodedConstParameter(
                short_name="p1", diag_coded_type=uint2, bit_position=0, **param_kwargs),
            CodedConstParameter(
                short_name="p2", diag_coded_type=uint2, bit_position=2, **param_kwargs),
            CodedConstParameter(
                short_name="p3", diag_coded_type=uint2, bit_position=3, **param_kwargs),
            CodedConstParameter(
                short_name="p4", diag_coded_type=uint1, bit_position=5, **param_kwargs),
            CodedConstParameter(
                short_name="p5", diag_coded_type=uint1, bit_position=6, **param_kwargs),
            CodedConstParameter(
                short_name="p6", diag_coded_type=uint1, bit_position=7, **param_kwargs),
        ]
        req = Request(
            odx_id=OdxLinkRef("request_id", doc_frags),
            short_name="request_sn",
            parameters=params,
            long_name=None,
            description=None,
            is_visible_raw=None,
            sdgs=[],
            byte_size=None,
        )
        self.assertFalse(req._BasicStructure__message_format_lines())


if __name__ == "__main__":
    unittest.main()
