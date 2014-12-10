import unittest 
from copy import deepcopy

from switchyard.lib.packet import *
from switchyard.lib.address import SpecialIPv6Addr
from switchyard.lib.pcapffi import PcapDumper

class IPv6PacketTests(unittest.TestCase):
    def setUp(self):
        self.e = Ethernet()
        self.e.ethertype = EtherType.IPv6
        self.ip = IPv6()
        self.ip.nextheader = IPProtocol.ICMPv6
        self.pkt = self.e + self.ip + ICMPv6()

    def testReconstruct(self):
        xbytes = self.pkt.to_bytes()
        pkt2 = Packet(raw=xbytes)
        self.assertEqual(self.pkt, pkt2)

    def testBlankAddrs(self):
        self.assertEqual(self.ip.srcip, SpecialIPv6Addr.UNDEFINED.value)
        self.assertEqual(self.ip.dstip, SpecialIPv6Addr.UNDEFINED.value)

    def testBadSet(self):
        with self.assertRaises(Exception):
            self.ip.ipdest = IPAddr('fe00::')

    def testBadProtocolType(self):
        # try to set an invalid protocol number
        with self.assertRaises(ValueError):
            self.ip.nextheader = 0xff

    def testRouteOpt(self):
        pkt = deepcopy(self.pkt)
        hopopt = IPv6RouteOption(IPv6Address("fd00::1"))
        idx = pkt.get_header_index(IPv6)
        pkt.insert_header(idx+1, hopopt)
        pkt[idx].nextheader = IPProtocol.IPv6RouteOption
        hopopt.nextheader = IPProtocol.ICMPv6

        xraw = pkt.to_bytes()
        p = Packet(raw=xraw)
        self.assertEqual(p, pkt)

    def testFragExtHdr(self):
        pkt = deepcopy(self.pkt)
        frag = IPv6Fragment(42, 1000, 0)
        idx = pkt.get_header_index(IPv6)
        pkt.insert_header(idx+1, frag)
        pkt[idx].nextheader = IPProtocol.IPv6Fragment
        frag.nextheader = IPProtocol.ICMPv6

        xraw = pkt.to_bytes()
        p = Packet(raw=xraw)
        self.assertEqual(p, pkt)        

        idx = p.get_header_index(IPv6Fragment)
        self.assertEqual(p[idx].id, 42)
        self.assertEqual(p[idx].offset, 1000)
        self.assertEqual(p[idx].mf, False)

    def testDestOptTunnelLimit(self):
        pkt = deepcopy(self.pkt)
        dstopt = IPv6DestinationOption()
        dstopt.add_option(TunnelEncapsulationLimit(0x13))
        dstopt.add_option(PadN(3))
        idx = pkt.get_header_index(IPv6)
        pkt.insert_header(idx+1, dstopt)
        pkt[idx].nextheader = IPProtocol.IPv6DestinationOption
        dstopt.nextheader = IPProtocol.ICMPv6
        xraw = pkt.to_bytes()
        p = Packet(raw=xraw)
        self.assertEqual(pkt, p)
        self.assertEqual(p[idx+1][0].limit, 0x13)

    def testHopOptRouterAlert(self):
        pkt = deepcopy(self.pkt)
        hopopt = IPv6HopOption()
        hopopt.add_option(RouterAlert(0x13))
        hopopt.add_option(PadN(2))
        idx = pkt.get_header_index(IPv6)
        pkt.insert_header(idx+1, hopopt)
        pkt[idx].nextheader = IPProtocol.IPv6HopOption
        hopopt.nextheader = IPProtocol.ICMPv6
        xraw = pkt.to_bytes()
        p = Packet(raw=xraw)
        self.assertEqual(pkt, p)
        self.assertEqual(hopopt[0].value, 0x13)

    def testHopOptHomeAddr(self):
        pkt = deepcopy(self.pkt)
        hopopt = IPv6HopOption()
        hopopt.nextheader = IPProtocol.ICMPv6
        hopopt.add_option(HomeAddress(IPv6Address("fc00::2")))
        hopopt.add_option(PadN(4))
        idx = pkt.get_header_index(IPv6)
        pkt.insert_header(idx+1, hopopt)
        pkt[idx].nextheader = IPProtocol.IPv6HopOption
        xraw = pkt.to_bytes()
        p = Packet(raw=xraw)
        self.assertEqual(pkt, p)

    def testBadPadding(self):
        pkt = deepcopy(self.pkt)
        hopopt = IPv6HopOption()
        hopopt.nextheader = IPProtocol.ICMPv6
        hopopt.add_option(HomeAddress(IPv6Address("fc00::2")))
        idx = pkt.get_header_index(IPv6)
        pkt.insert_header(idx+1, hopopt)
        pkt[idx].nextheader = IPProtocol.IPv6HopOption
        with self.assertLogs(level='WARNING') as cm:
            xraw = pkt.to_bytes()
        self.assertIn('not an even multiple of 8', cm.output[0])
        hopopt.add_option(PadN(4))
        xraw = pkt.to_bytes()
        p = Packet(raw=xraw)
        self.assertEqual(p, pkt)
        self.assertEqual(len(hopopt), 2)
        self.assertEqual(hopopt[0].address, IPv6Address("fc00::2"))
        with self.assertRaises(TypeError):
            x = hopopt[:1]
        with self.assertRaises(IndexError):
            x = hopopt[2]
        with self.assertRaises(IndexError):
            x = hopopt[-1]

    def testJumboPayload(self):
        pkt = deepcopy(self.pkt)
        destopt = IPv6DestinationOption()
        destopt.add_option(JumboPayload(10000))
        destopt.nextheader = IPProtocol.ICMPv6
        idx = pkt.get_header_index(IPv6)
        pkt.insert_header(idx+1, destopt)
        pkt[idx].nextheader = IPProtocol.IPv6DestinationOption
        xraw = pkt.to_bytes()
        p = Packet(raw=xraw)
        self.assertEqual(pkt, p)
        self.assertEqual(len(destopt), 1)
        self.assertEqual(destopt[0].len, 10000)

    def testNoNextHdr(self):
        pkt = deepcopy(self.pkt)
        idx = pkt.get_header_index(IPv6)
        pkt[idx].nextheader = IPProtocol.IPv6NoNext
        pkt[idx].srcip = IPv6Address("fc00::a")
        pkt[idx].dstip = IPv6Address("fc00::b")
        del pkt[idx+1] 
        self.assertEqual(pkt.num_headers(), 2)
        xraw = pkt.to_bytes()
        p = Packet(raw=xraw)
        self.assertEqual(p, pkt)

    def testMobilityHeader(self):
        pkt = deepcopy(self.pkt)
        idx = pkt.get_header_index(IPv6)
        pkt[idx].nextheader = IPProtocol.IPv6Mobility
        pkt[idx].srcip = IPv6Address("fc00::a")
        pkt[idx].dstip = IPv6Address("fc00::b")
        pkt[idx+1] = IPv6Mobility()
        self.assertEqual(pkt.num_headers(), 3)
        xraw = pkt.to_bytes()
        p = Packet(raw=xraw)
        xraw2 = p.to_bytes()
        self.assertEqual(pkt,p)

if __name__ == '__main__':
    unittest.main()
