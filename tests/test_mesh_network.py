import unittest
import time
import threading
from routing import RoutingTable, RouteEntry


class TestRoutingTable(unittest.TestCase):

    def setUp(self):
        self.routing_table = RoutingTable(max_route_age=5.0)
        self.routing_table.clear()

    def test_add_direct_route(self):
        self.routing_table.add_direct_route("peer_1")
        route = self.routing_table.get_route("peer_1")
        self.assertIsNotNone(route)
        self.assertEqual(route.metric, 0)
        self.assertTrue(route.is_direct)

    def test_add_indirect_route(self):
        success = self.routing_table.add_route(
            "peer_3", "peer_2", 1, ["peer_3", "peer_2"]
        )
        self.assertTrue(success)
        route = self.routing_table.get_route("peer_3")
        self.assertIsNotNone(route)
        self.assertEqual(route.metric, 1)
        self.assertEqual(route.next_hop_id, "peer_2")

    def test_route_replacement_better_metric(self):
        self.routing_table.add_route("peer_3", "peer_2", 2, ["peer_3", "peer_2"])
        route1 = self.routing_table.get_route("peer_3")
        self.assertEqual(route1.metric, 2)

        success = self.routing_table.add_route(
            "peer_3", "peer_4", 1, ["peer_3", "peer_4"]
        )
        self.assertTrue(success)
        route2 = self.routing_table.get_route("peer_3")
        self.assertEqual(route2.metric, 1)
        self.assertEqual(route2.next_hop_id, "peer_4")

    def test_route_max_metric_limit(self):
        success = self.routing_table.add_route(
            "peer_far", "peer_hop", 16, ["peer_far"]
        )
        self.assertFalse(success)

    def test_stale_route_removal(self):
        self.routing_table.add_route("peer_1", "peer_2", 1, ["peer_1", "peer_2"])
        time.sleep(6)
        stale = self.routing_table.remove_stale_routes()
        self.assertIn("peer_1", stale)
        route = self.routing_table.get_route("peer_1")
        self.assertIsNone(route)

    def test_direct_routes_persist(self):
        self.routing_table.add_direct_route("peer_1")
        time.sleep(6)
        stale = self.routing_table.remove_stale_routes()
        self.assertNotIn("peer_1", stale)
        route = self.routing_table.get_route("peer_1")
        self.assertIsNotNone(route)

    def test_peer_observation(self):
        self.routing_table.add_peer_observation("observer_1", ["peer_a", "peer_b"])
        direct_peers = self.routing_table.get_direct_peers()
        self.assertEqual(len(direct_peers), 0)

    def test_get_all_routes(self):
        self.routing_table.add_direct_route("peer_1")
        self.routing_table.add_route("peer_2", "peer_1", 1, ["peer_2", "peer_1"])
        all_routes = self.routing_table.get_all_routes()
        self.assertEqual(len(all_routes), 2)

    def test_distance_vector(self):
        self.routing_table.add_direct_route("peer_1")
        self.routing_table.add_route("peer_2", "peer_1", 1, ["peer_2", "peer_1"])
        dv = self.routing_table.compute_distance_vector("self")
        self.assertEqual(dv["self"], 0)
        self.assertEqual(dv["peer_1"], 0)
        self.assertEqual(dv["peer_2"], 1)

    def test_concurrent_access(self):
        errors = []

        def add_routes():
            try:
                for i in range(100):
                    self.routing_table.add_direct_route(f"peer_{i}")
            except Exception as e:
                errors.append(e)

        def get_routes():
            try:
                for i in range(100):
                    self.routing_table.get_route(f"peer_{i}")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=add_routes),
            threading.Thread(target=get_routes),
            threading.Thread(target=add_routes),
        ]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0)

    def test_clear_routing_table(self):
        self.routing_table.add_direct_route("peer_1")
        self.routing_table.add_direct_route("peer_2")
        self.routing_table.clear()
        self.assertEqual(len(self.routing_table.get_all_routes()), 0)


class TestMeshNetworkIntegration(unittest.TestCase):

    def test_three_device_chain_discovery(self):
        device_a = RoutingTable()
        device_b = RoutingTable()
        device_c = RoutingTable()

        device_a.add_direct_route("device_b")
        device_b.add_direct_route("device_a")
        device_b.add_direct_route("device_c")
        device_c.add_direct_route("device_b")

        device_a.add_route("device_c", "device_b", 1, ["device_c", "device_b"])
        device_c.add_route("device_a", "device_b", 1, ["device_a", "device_b"])

        route_a_to_c = device_a.get_route("device_c")
        self.assertIsNotNone(route_a_to_c)
        self.assertEqual(route_a_to_c.metric, 1)
        self.assertEqual(route_a_to_c.next_hop_id, "device_b")

        route_c_to_a = device_c.get_route("device_a")
        self.assertIsNotNone(route_c_to_a)
        self.assertEqual(route_c_to_a.metric, 1)
        self.assertEqual(route_c_to_a.next_hop_id, "device_b")

    def test_dynamic_topology_change(self):
        rt = RoutingTable()

        rt.add_direct_route("peer_a")
        rt.add_route("peer_b", "peer_a", 1, ["peer_b", "peer_a"])
        rt.add_route("peer_c", "peer_a", 2, ["peer_c", "peer_a"])

        self.assertIsNotNone(rt.get_route("peer_b"))
        self.assertIsNotNone(rt.get_route("peer_c"))

        rt.add_route("peer_c", "peer_b", 1, ["peer_c", "peer_b"])

        updated_route = rt.get_route("peer_c")
        self.assertEqual(updated_route.metric, 1)
        self.assertEqual(updated_route.next_hop_id, "peer_b")


if __name__ == "__main__":
    unittest.main()
