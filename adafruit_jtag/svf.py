
class JtagSvfParser(object):
    def __init__(self, jtag, svf_file):
        self.jtag = jtag
        self.svf_file = svf_file
        self.hdr = ["hdr", 0]
        self.hir = ["hir", 0]
        self.tdr = ["tdr", 0]
        self.tir = ["tir", 0]
        self.enddr = "DRPAUSE"
        self.endir = "IRPAUSE"
        self.loop_count = [0]

    def run(self):
        def field(cmd, name):
            num_bits = int(cmd[1])
            for k, v in ntuples(cmd, 2):
                if k == name:
                    return int(v, 16)

            if name == "mask" and "tdo" in cmd:
                return (2 ** num_bits) - 1
            else:
                return 0

        def runtest_field(cmd, name):
            for v, k in ntuples(cmd, 2):
                if k == name:
                    return v

            return None

        raw_svf_string = self.svf_file.read()
        no_comment_svf_string = re.sub('!.*?\r?\n', ' ', raw_svf_string)
        no_lines_string = re.sub(r'\s+', ' ', no_comment_svf_string)
        raw_cmd_strings = no_lines_string.lower().split(';')
        cmds = [re.sub(r'\(|\)', '', x).strip().split(' ') for x in raw_cmd_strings]

        loop_index = None
        self.loop_count = [0]
        cmd_index = 0

        while cmd_index < len(cmds):
            cmd = cmds[cmd_index]
            cmd_index = cmd_index + 1

            #print str(cmd)

            name = cmd[0]

            if name == "hdr":
                self.hdr = cmd

            if name == "hir":
                self.hir = cmd

            if name == "tdr":
                self.tdr = cmd

            if name == "tir":
                self.tir = cmd

            if name == "enddr":
                self.enddr = cmd[1].upper()

            if name == "endir":
                self.endir = cmd[1].upper()

            if name == "state":
                self.jtag.goto_state(cmd[1].upper())

            if name == "loop":
                self.loop_count = [int(cmd[1])] * 1000
                #print "loop (loop_count: %d)" % self.loop_count[0]
                loop_index = cmd_index

            if name == "endloop":
                #print "endloop (loop_count: %d)" % self.loop_count[0]
                if self.loop_count[0] is None:
                    loop_index = None
                else:
                    self.loop_count[0] = self.loop_count[0] - 1

                    if self.loop_count[0] > 0:
                        cmd_index = loop_index
                    else:
                        self.loop_count[0] = None
                        loop_index = None


            if name == "runtest":
                self.jtag.goto_state(cmd[1].upper())

                sleep_time = runtest_field(cmd, "sec")
                tck_count = runtest_field(cmd, "tck")

                if tck_count is None:
                    tck_count = 0
                else:
                    tck_count = int(tck_count)

                if sleep_time is not None:
                    tck_count = max(float(sleep_time) / 0.00001, tck_count)

                self.jtag.run(int(tck_count), 0)

            if name == "sir":
                self.jtag.goto_state("IRSHIFT")

                #tr_loc = int(self.hir[1]) + int(cmd[1])
                #r_loc = int(self.hir[1])
                #hr_loc = 0
                loop_count = self.loop_count
                def status_callback(match):
                    if loop_count[0] is not None:
                        if not match and loop_count[0] <= 1:
                            print("MISMATCH!")
                            print("cmd %d: %s" % (cmd_index, str(cmd)))
                            print("")
                            exit()

                        if match:
                            #print "SIR MATCH! " + str(loop_count)
                            loop_count[0] = 0

                self.jtag.shift(
                    int(cmd[1]),
                    #tdi =  (field(self.tir, "tdi")  << tr_loc) | (field(cmd, "tdi")  << r_loc) | (field(self.hir, "tdi")  << hr_loc),
                    #tdo =  (field(self.tir, "tdo")  << tr_loc) | (field(cmd, "tdo")  << r_loc) | (field(self.hir, "tdo")  << hr_loc),
                    #mask = (field(self.tir, "mask") << tr_loc) | (field(cmd, "mask") << r_loc) | (field(self.hir, "mask") << hr_loc)
                    tdi  = field(cmd, "tdi"),
                    tdo  = field(cmd, "tdo"),
                    mask = field(cmd, "mask"),
                    status_callback = status_callback
                )

                self.jtag.goto_state(self.endir)

            if name == "sdr":
                self.jtag.goto_state("DRSHIFT")

                shift_count = int(cmd[1])

                tr_loc = int(self.hdr[1]) + shift_count
                r_loc = int(self.hdr[1])
                hr_loc = 0

                loop_count = self.loop_count
                def status_callback(match):
                    if loop_count[0] is not None:
                        if not match and loop_count[0] <= 1:
                            print("MISMATCH!")
                            print("cmd %d: %s" % (cmd_index, str(cmd)))
                            print("")
                            exit()

                        if match:
                            #print "SDR MATCH! " + str(loop_count)
                            loop_count[0] = None

                self.jtag.shift(
                    int(cmd[1]),
                    #tdi =  (field(self.tdr, "tdi")  << tr_loc) | (field(cmd, "tdi")  << r_loc) | (field(self.hdr, "tdi")  << hr_loc),
                    #tdo =  (field(self.tdr, "tdo")  << tr_loc) | (field(cmd, "tdo")  << r_loc) | (field(self.hdr, "tdo")  << hr_loc),
                    #mask = (field(self.tdr, "mask") << tr_loc) | (field(cmd, "mask") << r_loc) | (field(self.hdr, "mask") << hr_loc)
                    tdi  = field(cmd, "tdi"),
                    tdo  = field(cmd, "tdo"),
                    mask = field(cmd, "mask"),
                    status_callback = status_callback
                )

                self.jtag.goto_state(self.enddr)

            self.jtag.pins.ser.task()


        self.jtag.pins.send()
