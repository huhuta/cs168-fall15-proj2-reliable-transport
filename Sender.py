from __future__ import print_function
import sys
import getopt
import BasicSender
from Checksum import validate_checksum


class Sender(BasicSender.BasicSender):
    # pylint: disable=W0621
    def __init__(self, dest, port, filename, debug=False, sackMode=False):
        super(Sender, self).__init__(dest, port, filename, debug)
        self.sackMode = sackMode
        self.debug = debug
        self.timeout = 0.4
        self.current_seqno = 0
        self.window = {}
        self.window_size = 7
        self.retransmit_count = 0

    def _retransmit(self):
        self.retransmit_count = 0
        unacknowledged_seqnos = [n for n in sorted(self.window.keys())
                                 if self.window[n] is not None]
        for seqno in unacknowledged_seqnos:
            self.send(self.window[seqno])

    def _check_fast_retransmit(self):
        if self.retransmit_count > 3:
            self.send(self.window[self.current_seqno])

    def _validate_ack_seqno_range(self, ack_seqno):
        if not ack_seqno:
            return False
        if ack_seqno > self.current_seqno + self.window_size:
            return False
        if ack_seqno < self.current_seqno + 1:
            self.retransmit_count += 1
            self._check_fast_retransmit()
            return False
        return True

    def _slide_window(self, ack_seqno):
        self.retransmit_count = 0
        for n in sorted(self.window.keys()):
            if n < ack_seqno:
                del self.window[n]
        self.current_seqno = ack_seqno

    def _update_window_as_sack_list(self, sack_list):
        if not sack_list:
            return
        int_sack_list = [int(x) for x in sack_list.split(',')]
        for sack in [x for x in int_sack_list if x in self.window.keys()]:
            self.window[sack] = None

    def _get_parsed_ack_seqno(self, msg):
        msg_type, seqno = self.split_packet(msg)[:2]
        if msg_type == 'ack':
            return int(seqno)

        if msg_type == 'sack':
            ack_seqno, sack_list = seqno.split(';')
            self._update_window_as_sack_list(sack_list)
            return int(ack_seqno)
        return None

    def _receive_packet_and_handle_it(self):
        msg = self.receive(timeout=self.timeout)
        if not msg:
            self._retransmit()
        if not validate_checksum(msg):
            return

        ack_seqno = self._get_parsed_ack_seqno(msg)
        if not self._validate_ack_seqno_range(ack_seqno):
            return
        self._slide_window(ack_seqno)

    def _handshake(self):
        syn = self.make_packet('syn', self.current_seqno, '')
        self.window[self.current_seqno] = syn
        self.send(syn)

    def _empty_out_window(self):
        while self.window:
            self._receive_packet_and_handle_it()

    def _adjust_window_boundary(self):
        while len(self.window) > self.window_size - 1:
            self._receive_packet_and_handle_it()

    def _send_actual_data(self, data):
        msg_type = 'dat' if data else 'fin'
        seqno = self.current_seqno + len(self.window)
        packet = self.make_packet(msg_type, seqno, data)
        self.window[seqno] = packet
        self.send(packet)

    def start(self):
        self._handshake()
        self._empty_out_window()

        data = None
        while data != '':
            self._adjust_window_boundary()
            data = self.infile.read(1200)
            self._send_actual_data(data)

        self.infile.close()
        self._empty_out_window()


if __name__ == "__main__":
    def usage():
        print("BEARS-TP Sender")
        print("-f FILE | --file=FILE The file to transfer;"
              " if empty reads from STDIN")
        print("-p PORT | --port=PORT The destination port, defaults to 33122")
        print("-a ADDRESS | --address=ADDRESS"
              " The receiver address or hostname,"
              " defaults to localhost")
        print("-d | --debug Print debug messages")
        print("-h | --help Print this usage message")
        print("-k | --sack Enable selective acknowledgement mode)")

    try:
        opts, args = getopt.getopt(
            sys.argv[1:],
            "f:p:a:dk", ["file=", "port=", "address=", "debug=", "sack="])
    except BaseException:
        usage()
        exit()

    port = 33122
    dest = "localhost"
    filename = None
    debug = False
    sackMode = False

    for o, a in opts:
        if o in ("-f", "--file="):
            filename = a
        elif o in ("-p", "--port="):
            port = int(a)
        elif o in ("-a", "--address="):
            dest = a
        elif o in ("-d", "--debug="):
            debug = True
        elif o in ("-k", "--sack="):
            sackMode = True

    s = Sender(dest, port, filename, debug, sackMode)
    try:
        s.start()
    except (KeyboardInterrupt, SystemExit):
        exit()
