#
#   HorusLib - Binary Packet Decoder Functions
#
import codecs
import struct
import time
from .delegates import *
from .checksums import *
from .payloads import HORUS_CUSTOM_FIELDS, HORUS_PAYLOAD_LIST, init_custom_field_list, init_payload_id_list



#
#   Horus Binary V1 and V2 Packet Formats
#
HORUS_PACKET_FORMATS = {
    'horus_binary_v1': {
        'name': 'Horus Binary v1 22 Byte Format',
        'length': 22,
        'struct': '<BH3sffHBBbBH',
        'checksum': 'crc16',
        'fields': [
            ['payload_id', 'payload_id'],
            ['sequence_number', 'none'],
            ['time', 'time_hms'],
            ['latitude', 'degree_float'],
            ['longitude', 'degree_float'],
            ['altitude', 'none'],
            ['speed', 'none'],
            ['satellites', 'none'],
            ['temperature', 'none'],
            ['battery_voltage', 'battery_5v_byte'],
            ['checksum', 'none']
        ]
    },
    'horus_binary_v2_16byte': {
        'name': 'Horus Binary v2 16 Byte Format',
        'length': 16,
        'struct': '<BBH3s3sHBBH',
        'checksum': 'crc16',
        'fields': [
            ['payload_id', 'payload_id'],
            ['sequence_number', 'none'],
            ['time', 'time_biseconds'],
            ['latitude', 'degree_fixed3'],
            ['longitude', 'degree_fixed3'],
            ['altitude', 'none'],
            ['battery_voltage', 'battery_5v_byte'],
            ['flags', 'none'],
            ['checksum', 'none']
        ]
    },
    'horus_binary_v2_32byte': {
        'name': 'Horus Binary v2 32 Byte Format',
        'length': 32,
        'struct': '<HH3sffHBBbB9sH',
        'checksum': 'crc16',
        'fields': [
            ['payload_id', 'payload_id'],
            ['sequence_number', 'none'],
            ['time', 'time_hms'],
            ['latitude', 'degree_float'],
            ['longitude', 'degree_float'],
            ['altitude', 'none'],
            ['speed', 'none'],
            ['satellites', 'none'],
            ['temperature', 'none'],
            ['battery_voltage', 'battery_5v_byte'],
            ['custom', 'custom'],
            ['checksum', 'none']
        ]
    }
}

# Lookup for packet length to the appropriate format.
HORUS_LENGTH_TO_FORMAT = {
    22: 'horus_binary_v1',
    16: 'horus_binary_v2_16byte',
    32: 'horus_binary_v2_32byte'
}

def decode_packet(data:bytes, packet_format:dict = None) -> dict:
    """ 
    Attempt to decode a set of bytes based on a provided packet format.

    """

    if packet_format is None:
        # Attempt to lookup the format based on the length of the data if it has not been provided.
        if len(data) in HORUS_LENGTH_TO_FORMAT:
            packet_format = HORUS_PACKET_FORMATS[HORUS_LENGTH_TO_FORMAT[len(data)]]


    # Output dictionary
    _output = {
        'packet_format': packet_format,
        'crc_ok': False,
        'payload_id': 0
        }
    
    # Check the length provided in the packet format matches up with the length defined by the struct.
    _struct_length = struct.calcsize(packet_format['struct'])
    if _struct_length != packet_format['length']:
        raise ValueError(f"Decoder - Provided length {packet_format['length']} and struct length ({_struct_length}) do not match!")
    
    # Check the length of the input data bytes matches that of the struct.
    if len(data) != _struct_length:
        raise ValueError(f"Decoder - Input data has length {len(data)}, should be length {_struct_length}.")

    # Check the Checksum
    _crc_ok = check_packet_crc(data, checksum=packet_format['checksum'])

    if not _crc_ok:
        raise ValueError("Decoder - CRC Failure.")
    else:
        _output['crc_ok'] = True

    # Now try and decode the data.
    _raw_fields = struct.unpack(packet_format['struct'], data)

    # Check the number of decoded fields is equal to the number of field definitions in the packet format.
    if len(_raw_fields) != len(packet_format['fields']):
        raise ValueError(f"Decoder - Packet format defines {len(packet_format['fields'])} fields, got {len(_raw_fields)} from struct.")

    # Now we can start extracting and formatting fields.
    
    _ukhas_fields = []
    for _i in range(len(_raw_fields)):
        _field_name = packet_format['fields'][_i][0]
        _field_type = packet_format['fields'][_i][1]
        _field_data = _raw_fields[_i]


        if _field_name == 'custom':
            # Attempt to interpret custom fields.
            # Note: This requires that the payload ID has been decoded prior to this field being parsed.
            if _output['payload_id'] in HORUS_CUSTOM_FIELDS:
                (_custom_data, _custom_str) = decode_custom_fields(_field_data, _output['payload_id'])

                # Add custom fields to string
                _ukhas_fields.append(_custom_str)

                # Add custom fields to output dict.
                for _field in _custom_data:
                    _output[_field] = _custom_data[_field]

        # Ignore checksum field. (and maybe other fields?)
        elif _field_name not in ['checksum']:
            # Decode field to string.
            (_decoded, _decoded_str) = decode_field(_field_type, _field_data)

            _output[_field_name] = _decoded

            _ukhas_fields.append(_decoded_str)


    # Convert to a UKHAS-compliant string.
    _ukhas_str = ",".join(_ukhas_fields)
    _ukhas_crc = ukhas_crc(_ukhas_str.encode('ascii'))
    _output['ukhas_str'] = "$$" + _ukhas_str + "*" + _ukhas_crc

    return _output


def hex_to_bytes(data:str) -> bytes:
    """ Convert a string of hexadeximal digits to a bytes representation """
    try:
        _binary_string = codecs.decode(data, 'hex')
        return _binary_string
    except TypeError as e:
        logging.error("Error parsing line as hexadecimal (%s): %s" % (str(e), data))
        return None


if __name__ == "__main__":
    import argparse
    import sys


    # Read command-line arguments
    parser = argparse.ArgumentParser(description="Project Horus Binary Telemetry Decoder", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--test", action="store_true", default=False, help="Run unit tests.")
    parser.add_argument("--update", action="store_true", default=False, help="Download latest payload ID and custom fields files before continuing.")
    parser.add_argument("--decode", type=str, default=None, help="Attempt to decode a hexadecial packet.")
    parser.add_argument("-v", "--verbose", action="store_true", default=False, help="Verbose output (set logging level to DEBUG)")
    args = parser.parse_args()

    if args.verbose:
        _log_level = logging.DEBUG
    else:
        _log_level = logging.INFO

    # Setup Logging
    logging.basicConfig(
        format="%(asctime)s %(levelname)s: %(message)s", level=_log_level
    )

    if args.update:
        init_payload_id_list()
        init_custom_field_list()
    
    if args.decode is not None:
        try:
            _decoded = decode_packet(hex_to_bytes(args.decode))
            print(f"Decoded UKHAS String: {_decoded['ukhas_str']}")
        except ValueError as e:
            print(f"Error while decoding: {str(e)}")


    if args.test:

        tests = [
            ['horus_binary_v1', b'\x01\x12\x00\x00\x00\x23\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x1C\x9A\x95\x45', ''],
            ['horus_binary_v1', b'\x01\x12\x00\x00\x00\x23\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x1C\x9A\x95\x45', 'error'],
            ['horus_binary_v2_16byte', b'\x01\x12\x02\x00\x02\xbc\xeb!AR\x10\x00\xff\x00\xe1\x7e', ''],
            #                             id      seq_no  HH   MM  SS  lat             lon            alt     spd sat tmp bat custom data -----------------------| crc16
            ['horus_binary_v2_32byte', b'\xFF\xFF\x12\x00\x00\x00\x23\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xe8\x82', '']
        ]

        for _test in tests:
            _format = _test[0]
            _input = _test[1]
            _output = _test[2]

            try:
                _decoded = decode_packet(_input)
                print(f"Input ({_format}): {str(_input)} - Output: {_decoded['ukhas_str']}")
                print(_decoded)
                # Insert assert checks here.

            except ValueError as e:
                print(f"Input ({_format}): {str(_input)} - Caught Error: {str(e)}")
                assert(_output == 'error')


        print("All tests passed!")

