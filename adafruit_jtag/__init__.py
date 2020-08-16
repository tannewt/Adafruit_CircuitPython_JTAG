import time

def ntuples(lst, n):
    return list(zip(*[lst[i:]+lst[:i] for i in range(n)]))

class _JtagStateMachine(object):
    def __init__(self):
        self.states = {
            "RESET": ("IDLE", "RESET"),
            "IDLE": ("IDLE", "DRSELECT"),

            "DRSELECT": ("DRCAPTURE", "IRSELECT"),
            "DRCAPTURE": ("DRSHIFT", "DREXIT1"),
            "DRSHIFT": ("DRSHIFT", "DREXIT1"),
            "DREXIT1": ("DRPAUSE", "DRUPDATE"),
            "DRPAUSE": ("DRPAUSE", "DREXIT2"),
            "DREXIT2": ("DRSHIFT", "DRUPDATE"),
            "DRUPDATE": ("IDLE", "DRSELECT"),

            "IRSELECT": ("IRCAPTURE", "RESET"),
            "IRCAPTURE": ("IRSHIFT", "IREXIT1"),
            "IRSHIFT": ("IRSHIFT", "IREXIT1"),
            "IREXIT1": ("IRPAUSE", "IRUPDATE"),
            "IRPAUSE": ("IRPAUSE", "IREXIT2"),
            "IREXIT2": ("IRSHIFT", "IRUPDATE"),
            "IRUPDATE": ("IDLE", "DRSELECT")
        }

        self.memo = {}

    def shortest_path(self, source, target):
        """
        This function implements Dijkstra's Algorithm almost exactly as it is
        written on Wikipedia.

        https://en.wikipedia.org/wiki/Dijkstra%27s_algorithm
        """
        INFINITY = 1000
        UNDEFINED = None

        q = set()
        dist = {}
        prev = {}

        for v in self.states:
            dist[v] = INFINITY
            prev[v] = UNDEFINED
            q.add(v)

        dist[source] = 0

        while len(q) != 0:
            u = min(q, key = lambda x: dist[x])
            q.remove(u)

            for v in self.states[u]:
                alt = dist[u] + 1
                if alt < dist[v]:
                    dist[v] = alt
                    prev[v] = u

        s = []
        u = target
        while prev[u] is not None:
            s.insert(0, u)
            u = prev[u]

        s.insert(0, u)

        return s


    def get_tms_sequence(self, source, target):
        memo_key = (source, target)
        if memo_key in self.memo:
            return self.memo[memo_key]

        def get_tms(pair):
            (src, dst) = pair
            if self.states[src][0] == dst:
                return 0
            elif self.states[src][1] == dst:
                return 1
            else:
                return None

        path = self.shortest_path(source, target)
        tms_sequence = [get_tms(p) for p in ntuples(path, 2)][:-1]
        self.memo[memo_key] = tms_sequence

        return tms_sequence

class Jtag:
    def __init__(self, *, tck, tms, tdi, tdo):
        self._tck = tck
        self._tms = tms
        self._tdi = tdi
        self._tdo = tdo

        ### manually set TMS, TCK, and TDI to output and TDO to input
        tck.switch_to_output()
        tms.switch_to_output()
        tdi.switch_to_output()
        tdo.switch_to_input()

        self.sm = _JtagStateMachine()
        self._current_state = None

    def _clock(self):
        self._tck.value = False
        self._tck.value = True

    def run_tms(self, tms_sequence):
        for tms in tms_sequence:
            self._tms.value = tms
            self._clock()

    def run(self, tclks, tms):
        self._tms.value = tms

        for i in range(tclks):
            self._clock()

    def runtest(self, tclks, state="IDLE"):
        self.goto_state(state)
        for i in range(tclks):
            self._clock()

    def _shift_tdi(self, num_bits, write_data):
        for bit in range(num_bits):
            if isinstance(write_data, bool):
                if bit == 0:
                    self._tdi.value = write_data
            elif isinstance(write_data, int):
                self._tdi.value = (write_data & (1 << bit)) != 0
            else:
                self._tdi.value = (write_data[bit // 8] & (1 << (bit % 8))) != 0
            self._tms.value = bit == num_bits - 1
            self._clock()

    def _shift_tdo(self, num_bits, buf):
        for bit in range(num_bits):
            if bit % 8 == 0:
                buf[bit // 8] = 0
            self._tms.value = bit == num_bits - 1
            self._clock()
            if self._tdo.value:
                buf[bit // 8] |= 1 << (bit % 8)

    def write_ir(self, num_bits, write_data):
         self.goto_state("IRSHIFT")
         self._shift_tdi(num_bits, write_data)
         self._current_state = self.sm.states[self._current_state][1]
         self.goto_state("IRPAUSE")

    def read_dr(self, num_bits, buf):
         self.goto_state("DRSHIFT")
         self._shift_tdo(num_bits, buf)
         self._current_state = self.sm.states[self._current_state][1]
         self.goto_state("DRPAUSE")

    def write_dr(self, num_bits, buf):
         self.goto_state("DRSHIFT")
         self._shift_tdi(num_bits, buf)
         self._current_state = self.sm.states[self._current_state][1]
         self.goto_state("DRPAUSE")

    def goto_state(self, target_state):
        # print(self._current_state, "->", target_state)
        tms_sequence = []

        if self._current_state is None:
            # we don't know what state we're in, so we will force ourselves
            # into the Reset state before we start moving anywhere
            self._current_state = "RESET"
            self.run_tms([1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1])

        self.run_tms(self.sm.get_tms_sequence(self._current_state, target_state))
        self._current_state = target_state
