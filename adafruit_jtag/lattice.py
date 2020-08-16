
class BitstreamFile(object):
    def __init__(self, bit_file):
        self.cfg_data = None
        self.ebr_data = None
        self.ufm_data = None
        self.feature_row = None
        self.feature_bits = None
        self.last_note = ""
        self._parse(bit_file)

    def numRows(self):
        def toInt(list_or_none):
            if list_or_none is None:
                return 0
            else:
                return len(list_or_none)

        return toInt(self.cfg_data) + toInt(self.ebr_data) + toInt(self.ufm_data)

    def _parse(self, bit):
        def bytestring_reverse_to_int(bytestr):
            rev_line = []
            for l in reversed(bytestr):
                b = bin(l)
                b_rev = b[-1:1:-1]
                b_rev = b_rev + (8 - len(b_rev))*'0'
                rev_line.append(int(b_rev, 2))

            return int.from_bytes(rev_line, byteorder='big')

        def line_to_int(line):
            try:
                return int(line[::-1], 16)
            except:
                traceback.print_exc()
                return None

        # Validate we have a bitstream.
        if bit.read(2) != b"\xff\x00":
            raise ValueError("Bitstream file does not begin with 0xFF00.")

        while True:
            val = bit.read(1)
            if bit.peek(4)[:4] == b"\xff\xff\xbd\xb3":
                break
            if not val:
                raise ValueError("Could not find bitstream preamble.")

        start_of_data = bit.tell()

        # Eat characters and commands until we find a compressed bitstream.
        bit.read(4)
        while True:
            cmd = bit.read(1)

            # BYPASS
            if cmd == b"\xff":
                pass
            # LSC_RESET_CRC
            elif cmd == b"\x3b":
                bit.read(3)
            # VERIFY_ID
            elif cmd == b"\xe2":
                bit.read(7)
            # LSC_WRITE_COMP_DIC
            elif cmd == b"\x02":
                bit.read(11)
            # LSC_PROG_CNTRL0
            elif cmd == b"\x22":
                bit.read(7)
            # LSC_INIT_ADDRESS
            elif cmd == b"\x46":
                bit.read(3)
            # LSC_PROG_INCR_CMP
            elif cmd == b"\xb8":
                break
            # LSC_PROG_INCR_RTI
            elif cmd == b"\x82":
                raise ValueError("Bitstream is not compressed- not writing.")
            else:
                assert False, "Unknown command type {}.".format(cmd)

        bit.seek(start_of_data)

        data = []
        done = False
        while not done:
            line = bit.read(16)

            if len(line) < 16:
                line = line + b"\xff" * (16 - len(line))
                done = True

            data.append(bytestring_reverse_to_int(line))

        self.cfg_data = data
        self.feature_row = 0
        self.feature_bits = int("0000010001100000", 2)
