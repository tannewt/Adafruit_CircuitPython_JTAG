
class JtagCustomProgrammer(object):
    def __init__(self, jtag):
        self.jtag = jtag
        self.enddr = "DRPAUSE"
        self.endir = "IRPAUSE"
        self.config_data = None

    def write_ir(self, num_bits, write_data):
         self.jtag.goto_state("IRSHIFT")
         self.jtag.pins.shift_tdi(num_bits, write_data)
         self.jtag.current_state = self.jtag.sm.states[self.jtag.current_state][1]
         self.jtag.goto_state("IRPAUSE")

    def read_dr(self, num_bits, read_callback, blocking = False):
         self.jtag.goto_state("DRSHIFT")
         self.jtag.pins.shift_tdo(num_bits, read_callback, blocking = blocking)
         self.jtag.current_state = self.jtag.sm.states[self.jtag.current_state][1]
         self.jtag.goto_state("DRPAUSE")

    def write_dr(self, num_bits, write_data):
         self.jtag.goto_state("DRSHIFT")
         self.jtag.pins.shift_tdi(num_bits, write_data)
         self.jtag.current_state = self.jtag.sm.states[self.jtag.current_state][1]
         self.jtag.goto_state("DRPAUSE")

    def check_dr(self, num_bits, check_data, check_mask, status_callback = None):
         self.jtag.goto_state("DRSHIFT")
         self.jtag.pins.shift_tdo_poll(num_bits, check_data, check_mask, status_callback)
         self.jtag.current_state = self.jtag.sm.states[self.jtag.current_state][1]
         self.jtag.goto_state("DRPAUSE")

    def runtest(self, clks, state = "IDLE"):
        self.jtag.goto_state(state)

        while clks > 0:
            clks_now = min(clks, 1000)
            self.jtag.pins.run_tck(clks_now)
            clks -= clks_now

    def loop(self, loop_count):
        self.jtag.pins.loop(loop_count)

    def endloop(self):
        self.jtag.pins.end_loop(None)



    def program(self, jed_file, progress = None):
        num_rows = jed_file.numRows()
        prog_update_freq = 20
        prog_update_cnt = 0

        def default_progress(v):
            pass

        if progress is None:
            progress = default_progress

        def status(description, amount):
            def status_callback(status):
                if len(status) == 0:
                    progress(description)
                    progress(amount)

                elif status[0] == 0:
                    progress(description)
                    progress(amount)

                else:
                    progress(description + " - Failed!")

            return status_callback

        # drain any lingering read data before continuing
        if self.jtag.pins.ser.ser.inWaiting() > 0:
            print(str([x for x in array.array('B', self.jtag.pins.ser.ser.read(size = self.jtag.pins.ser.ser.inWaiting())).tolist()]))

        self.jtag.pins.clear_status()

        ### read idcode
        # This is constantly being checked in the GUI
        #self.write_ir(8, 0xE0)
        #self.check_dr(32, 0x012BA043, 0xFFFFFFFF)

        ### program bscan register
        self.write_ir(8, 0x1C)
        self.write_dr(208, 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF)

        ### check key protection fuses
        self.write_ir(8, 0x3C)
        self.runtest(1000)
        self.check_dr(32, 0x00000000, 0x00010000)

        ### enable the flash
        # ISC ENABLE
        self.write_ir(8, 0xC6)
        self.write_dr(8, 0x00)
        self.runtest(1000)
        # ISC ERASE
        self.write_ir(8, 0x0E)
        self.write_dr(8, 0x01)
        self.runtest(1000)
        # BYPASS
        self.write_ir(8, 0xFF)
        # ISC ENABLE
        self.write_ir(8, 0xC6)
        self.write_dr(8, 0x08)
        self.runtest(1000)

        ### check the OTP fuses
        # LSC_READ_STATUS
        self.write_ir(8, 0x3C)
        self.runtest(1000)
        self.check_dr(32, 0x00000000, 0x00024040)

        progress("Erasing configuration flash")
        ### erase the flash
        # ISC ERASE
        self.write_ir(8, 0x0E)
        self.write_dr(8, 0x0E)
        self.runtest(1000)
        # LSC_CHECK_BUSY
        self.write_ir(8, 0xF0)
        self.loop(10000)
        self.runtest(1000)
        self.check_dr(1, 0, 1)
        self.endloop()
        self.jtag.pins.get_status(status("Writing bitstream", num_rows), blocking = True)

        ### read the status bit
        # LSC_READ_STATUS
        self.write_ir(8, 0x3C)
        self.runtest(1000)
        self.check_dr(32, 0x00000000, 0x00003000)

        ### program config flash
        # LSC_INIT_ADDRESS
        self.write_ir(8, 0x46)
        self.write_dr(8, 0x04)
        self.runtest(1000)

        row_count = num_rows
        combined_cfg_data = jed_file.cfg_data

        if jed_file.ebr_data is not None:
            combined_cfg_data += jed_file.ebr_data

        for line in combined_cfg_data:
            # LSC_PROG_INCR_NV
            self.write_ir(8, 0x70)
            self.write_dr(128, line)
            self.runtest(2)
            # LSC_CHECK_BUSY
            self.write_ir(8, 0xF0)
            self.loop(10000)
            self.runtest(100)
            self.check_dr(1, 0, 1)
            self.endloop()

            prog_update_cnt += 1

            if prog_update_cnt % prog_update_freq == 0:
                self.jtag.pins.get_status(status("Writing bitstream", prog_update_freq), blocking = True)

        if jed_file.ufm_data is not None:
            ### program user flash
            # LSC_INIT_ADDRESS
            self.write_ir(8, 0x47)
            self.runtest(1000)

            for line in jed_file.ufm_data:
                # LSC_PROG_INCR_NV
                self.write_ir(8, 0x70)
                self.write_dr(128, line)
                self.runtest(2)
                # LSC_CHECK_BUSY
                self.write_ir(8, 0xF0)
                self.loop(10000)
                self.runtest(100)
                self.check_dr(1, 0, 1)
                self.endloop()

                prog_update_cnt += 1

                if prog_update_cnt % prog_update_freq == 0:
                    self.jtag.pins.get_status(status("Writing bitstream", prog_update_freq), blocking = True)

        ### verify config flash
        # LSC_INIT_ADDRESS
        self.write_ir(8, 0x46)
        self.write_dr(8, 0x04)
        self.runtest(1000)

        # LSC_READ_INCR_NV
        self.write_ir(8, 0x73)
        self.feature_row = None
        self.feature_bits = None

        for line in combined_cfg_data:
            self.runtest(2)
            self.check_dr(128, line, 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF)

            prog_update_cnt += 1

            if prog_update_cnt % prog_update_freq == 0:
                self.jtag.pins.get_status(status("Verifying bitstream", prog_update_freq), blocking = True)

        if jed_file.ufm_data is not None:
            ### verify user flash
            # LSC_INIT_ADDRESS
            self.write_ir(8, 0x47)
            self.runtest(1000)

            # LSC_READ_INCR_NV
            self.write_ir(8, 0x73)

            for line in jed_file.ufm_data:
                self.runtest(2)
                self.check_dr(128, line, 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF)

                prog_update_cnt += 1

                if prog_update_cnt % prog_update_freq == 0:
                    self.jtag.pins.get_status(status("Verifying bitstream", prog_update_freq), blocking = True)


        self.jtag.pins.get_status(status("Writing and verifying feature rows", 0), blocking = True)
        ### program feature rows
        # LSC_INIT_ADDRESS
        self.write_ir(8, 0x46)
        self.write_dr(8, 0x02)
        self.runtest(2)
        # LSC_PROG_FEATURE
        self.write_ir(8, 0xE4)
        self.write_dr(64, jed_file.feature_row)
        self.runtest(2)
        # LSC_CHECK_BUSY
        self.write_ir(8, 0xF0)
        self.loop(10000)
        self.runtest(100)
        self.check_dr(1, 0, 1)
        self.endloop()
        # LSC_READ_FEATURE
        self.write_ir(8, 0xE7)
        self.runtest(2)
        self.check_dr(64, jed_file.feature_row, 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF)
        # LSC_PROG_FEABITS
        self.write_ir(8, 0xF8)
        self.write_dr(16, jed_file.feature_bits)
        self.runtest(2)
        # LSC_CHECK_BUSY
        self.write_ir(8, 0xF0)
        self.loop(10000)
        self.runtest(100)
        self.check_dr(1, 0, 1)
        self.endloop()
        # LSC_READ_FEABITS
        self.write_ir(8, 0xFB)
        self.runtest(2)
        self.check_dr(16, jed_file.feature_bits, 0xFFFF)

        ### read the status bit
        self.write_ir(8, 0x3C)
        self.runtest(2)
        self.check_dr(32, 0x00000000, 0x00003000)

        ### program done bit
        # ISC PROGRAM DONE
        self.write_ir(8, 0x5E)
        self.runtest(2)
        self.write_dr(8, 0xF0)
        # LSC_CHECK_BUSY
        self.write_ir(8, 0xF0)
        self.loop(10000)
        self.runtest(100)
        self.check_dr(1, 0, 1)
        self.endloop()
        # BYPASS
        self.write_ir(8, 0xFF)

        ### exit programming mode
        # ISC DISABLE
        self.write_ir(8, 0x26)
        self.runtest(1000)
        # ISC BYPASS
        self.write_ir(8, 0xFF)
        self.runtest(1000)

        ### verify sram done bit
        self.runtest(10000)
        # LSC_READ_STATUS
        self.write_ir(8, 0x3C)
        self.check_dr(32, 0x00000100, 0x00002100)

        self.jtag.goto_state("RESET")

        self.jtag.pins.get_status(status("Done", 0), blocking = True)
