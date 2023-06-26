"""
Agent documentation goes here.
"""

__docformat__ = "reStructuredText"

import logging
import sys

from volttron.platform.messaging import headers

from volttron.platform.agent.utils import format_timestamp, get_aware_utc_now
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC

from datetime import timedelta, datetime, timezone

import pandas as pd

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


def load_me(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Loadshed
    :rtype: Loadshed
    """
    try:
        global config
        config = utils.load_config(config_path)
        _log.info(f"[LBS Agent INFO] - debug config {config}")
    except Exception:
        config = {}

    if not config:
        _log.info("[LBS Agent INFO] - Using Agent defaults for starting configuration.")

    return LbsWifi(**kwargs)


class LbsWifi(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, config_path, **kwargs):
        super(LbsWifi, self).__init__(**kwargs)
        _log.info("[LBS Agent INFO] - vip_identity: " + self.core.identity)

        self.default_config = {
            "building_topic": "slipstream_internal/slipstream_hq",
            "nested_group_map": {"vavs": {"device_address": "25", "point": ["SA-F"]}},
        }

        # self.building_topic = str(self.default_config["building_topic"])
        # self.nested_group_map = dict(self.default_config["nested_group_map"])

        self.bacnet_cmds_is_running = False
        self.zone1_lv = 0
        self.zone2_lv = 0
        self.zone3_lv = 0
        self.bas_points_that_are_written = []
        self.bacnet_overrides_on_bas = False

        self.per_person_cfm_req = 5
        self.office_per_sqft_cfm_req = 0.06
        self.EZ1 = 0.80
        self.total_flow_temp = 0
        self.percent_oa = 0

        self.vav_last_scan = get_aware_utc_now()
        self.zone_sqft_vav = 1480

        self.ahu_oa_dpr_cmd = 0
        self.ahu_oa_dpr_point = "Outdoor Air Damper Command"

        self.pub_sub_subscriptions = []
        self.building_topic = "devices/slipstream_internal/slipstream_hq/"
        self.wifi_prefix = "lbs"
        self.ahu_prefix = "1100"
        self.calcs_pub_str = (
            f"{self.building_topic + self.wifi_prefix}/analysis/{self.ahu_prefix}/all"
        )

        self.device_config = {
            1: {
                "name": "vav_25",
                "address": "25",
                "flow_point": "SA-F",
                "zone_temp_point": "SA-F",
                "zone_temp_spt_point": "ZN-SP",
                "air_damper_point": "DPR-O",
                "zone_621_control": False,
                "flow_spt_override_control": True,
                "units": "imperial",
            },
            2: {
                "name": "vav_24",
                "address": "24",
                "flow_point": "SA-F",
                "zone_temp_point": "SA-F",
                "zone_temp_spt_point": "ZN-SP",
                "air_damper_point": "DPR-O",
                "zone_621_control": False,
                "flow_spt_override_control": True,
                "units": "imperial",
            },
            3: {
                "name": "vav_36",
                "address": "36",
                "flow_point": "SA-F",
                "zone_temp_point": "SA-F",
                "zone_temp_spt_point": "ZN-SP",
                "air_damper_point": "DPR-O",
                "zone_621_control": False,
                "flow_spt_override_control": True,
                "units": "imperial",
            },
            4: {
                "name": "vav_30",
                "address": "30",
                "flow_point": "SA-F",
                "zone_temp_point": "SA-F",
                "zone_temp_spt_point": "ZN-SP",
                "air_damper_point": "DPR-O",
                "zone_621_control": False,
                "flow_spt_override_control": True,
                "units": "imperial",
            },
            5: {
                "name": "vav_34",
                "address": "34",
                "flow_point": "SA-F",
                "zone_temp_point": "SA-F",
                "zone_temp_spt_point": "ZN-SP",
                "air_damper_point": "DPR-O",
                "zone_621_control": False,
                "flow_spt_override_control": True,
                "units": "imperial",
            },
            6: {
                "name": "vav_27",
                "address": "27",
                "flow_point": "SA-F",
                "zone_temp_point": "SA-F",
                "zone_temp_spt_point": "ZN-SP",
                "air_damper_point": "DPR-O",
                "zone_621_control": False,
                "flow_spt_override_control": True,
                "units": "imperial",
            },
            7: {
                "name": "vav_31",
                "address": "31",
                "flow_point": "SA-F",
                "zone_temp_point": "SA-F",
                "zone_temp_spt_point": "ZN-SP",
                "air_damper_point": "DPR-O",
                "zone_621_control": False,
                "flow_spt_override_control": True,
                "units": "imperial",
            },
            8: {
                "name": "vav_29",
                "address": "29",
                "flow_point": "SA-F",
                "zone_temp_point": "SA-F",
                "zone_temp_spt_point": "ZN-SP",
                "air_damper_point": "DPR-O",
                "zone_621_control": False,
                "flow_spt_override_control": True,
                "units": "imperial",
            },
            9: {
                "name": "vav_14",
                "address": "14",
                "flow_point": "SA-F",
                "zone_temp_point": "SA-F",
                "zone_temp_spt_point": "ZN-SP",
                "air_damper_point": "DPR-O",
                "zone_621_control": False,
                "flow_spt_override_control": True,
                "units": "imperial",
            },
            10: {
                "name": "vav_13",
                "address": "13",
                "flow_point": "SA-F",
                "zone_temp_point": "SA-F",
                "zone_temp_spt_point": "ZN-SP",
                "air_damper_point": "DPR-O",
                "zone_621_control": False,
                "flow_spt_override_control": True,
                "units": "imperial",
            },
            11: {
                "name": "vav_15",
                "address": "15",
                "flow_point": "SA-F",
                "zone_temp_point": "SA-F",
                "zone_temp_spt_point": "ZN-SP",
                "air_damper_point": "DPR-O",
                "zone_621_control": False,
                "flow_spt_override_control": True,
                "units": "imperial",
            },
            12: {
                "name": "vav_11",
                "address": "11",
                "flow_point": "SA-F",
                "zone_temp_point": "SA-F",
                "zone_temp_spt_point": "ZN-SP",
                "air_damper_point": "DPR-O",
                "zone_621_control": False,
                "flow_spt_override_control": True,
                "units": "imperial",
            },
            13: {
                "name": "vav_9",
                "address": "9",
                "flow_point": "SA-F",
                "zone_temp_point": "SA-F",
                "zone_temp_spt_point": "ZN-SP",
                "air_damper_point": "DPR-O",
                "zone_621_control": False,
                "flow_spt_override_control": True,
                "units": "imperial",
            },
            14: {
                "name": "vav_21",
                "address": "21",
                "flow_point": "SA-F",
                "zone_temp_point": "SA-F",
                "zone_temp_spt_point": "ZN-SP",
                "air_damper_point": "DPR-O",
                "zone_621_control": False,
                "flow_spt_override_control": True,
                "units": "imperial",
            },
            15: {
                "name": "vav_16",
                "address": "16",
                "flow_point": "SA-F",
                "zone_temp_point": "SA-F",
                "zone_temp_spt_point": "ZN-SP",
                "air_damper_point": "DPR-O",
                "zone_621_control": False,
                "flow_spt_override_control": True,
                "units": "imperial",
            },
            16: {
                "name": "vav_8",
                "address": "8",
                "flow_point": "SA-F",
                "zone_temp_point": "SA-F",
                "zone_temp_spt_point": "ZN-SP",
                "air_damper_point": "DPR-O",
                "zone_621_control": False,
                "flow_spt_override_control": True,
                "units": "imperial",
            },
            17: {
                "name": "vav_10",
                "address": "10",
                "flow_point": "SA-F",
                "zone_temp_point": "SA-F",
                "zone_temp_spt_point": "ZN-SP",
                "air_damper_point": "DPR-O",
                "zone_621_control": False,
                "flow_spt_override_control": True,
                "units": "imperial",
            },
            18: {
                "name": "vav_19",
                "address": "19",
                "flow_point": "SA-F",
                "zone_temp_point": "SA-F",
                "zone_temp_spt_point": "ZN-SP",
                "air_damper_point": "DPR-O",
                "zone_621_control": False,
                "flow_spt_override_control": True,
                "units": "imperial",
            },
            19: {
                "name": "vav_20",
                "address": "20",
                "flow_point": "SA-F",
                "zone_temp_point": "SA-F",
                "zone_temp_spt_point": "ZN-SP",
                "air_damper_point": "DPR-O",
                "zone_621_control": False,
                "flow_spt_override_control": True,
                "units": "imperial",
            },
            20: {
                "name": "vav_37",
                "address": "37",
                "flow_point": "SA-F",
                "zone_temp_point": "SA-F",
                "zone_temp_spt_point": "ZN-SP",
                "air_damper_point": "DPR-O",
                "zone_621_control": False,
                "flow_spt_override_control": True,
                "units": "imperial",
            },
            21: {
                "name": "vav_38",
                "address": "38",
                "flow_point": "SA-F",
                "zone_temp_point": "SA-F",
                "zone_temp_spt_point": "ZN-SP",
                "air_damper_point": "DPR-O",
                "zone_621_control": False,
                "flow_spt_override_control": True,
                "units": "imperial",
            },
            22: {
                "name": "vav_39",
                "address": "39",
                "flow_point": "SA-F",
                "zone_temp_point": "SA-F",
                "zone_temp_spt_point": "ZN-SP",
                "air_damper_point": "DPR-O",
                "zone_621_control": False,
                "flow_spt_override_control": True,
                "units": "imperial",
            },
            23: {
                "name": "vav_12023",
                "address": "12023",
                "flow_point": "Discharge Air Flow",
                "zone_temp_point": "Space Temperature Active",
                "zone_temp_spt_point": "Space Temperature Setpoint Active",
                "air_damper_point": "Air Valve Position Command",
                "zone_621_control": False,
                "flow_spt_override_control": True,
                "units": "metric",
            },
            24: {
                "name": "vav_12035",
                "address": "12035",
                "flow_point": "Discharge Air Flow",
                "zone_temp_point": "Space Temperature Active",
                "zone_temp_spt_point": "Space Temperature Setpoint Active",
                "air_damper_point": "Air Valve Position Command",
                "zone_621_control": False,
                "flow_spt_override_control": True,
                "units": "metric",
            },
            25: {
                "name": "vav_12026",
                "address": "12026",
                "flow_point": "Discharge Air Flow",
                "zone_temp_point": "Space Temperature Active",
                "zone_temp_spt_point": "Space Temperature Setpoint Active",
                "air_damper_point": "Air Valve Position Command",
                "zone_621_control": False,
                "flow_spt_override_control": True,
                "units": "metric",
            },
            26: {
                "name": "vav_12028",
                "address": "12028",
                "flow_point": "Discharge Air Flow",
                "zone_temp_point": "Space Temperature Active",
                "zone_temp_spt_point": "Space Temperature Setpoint Active",
                "air_damper_point": "Air Valve Position Command",
                "zone_621_control": False,
                "flow_spt_override_control": True,
                "units": "metric",
            },
            27: {
                "name": "vav_12032",
                "address": "12032",
                "flow_point": "Discharge Air Flow",
                "zone_temp_point": "Space Temperature Active",
                "zone_temp_spt_point": "Space Temperature Setpoint Active",
                "air_damper_point": "Air Valve Position Command",
                "zone_621_control": False,
                "flow_spt_override_control": True,
                "units": "metric",
            },
            28: {
                "name": "vav_12033",
                "address": "12033",
                "flow_point": "Discharge Air Flow",
                "zone_temp_point": "Space Temperature Active",
                "zone_temp_spt_point": "Space Temperature Setpoint Active",
                "air_damper_point": "Air Valve Position Command",
                "zone_621_control": False,
                "flow_spt_override_control": True,
                "units": "metric",
            },
            29: {
                "name": "vav_11002",
                "address": "11002",
                "flow_point": "Discharge Air Flow",
                "zone_temp_point": "Space Temperature Active",
                "zone_temp_spt_point": "Space Temperature Setpoint Active",
                "air_damper_point": "Air Valve Position Command",
                "zone_621_control": False,
                "flow_spt_override_control": True,
                "units": "metric",
            },
            30: {
                "name": "vav_11007",
                "address": "11007",
                "flow_point": "Discharge Air Flow",
                "zone_temp_point": "Space Temperature Active",
                "zone_temp_spt_point": "Space Temperature Setpoint Active",
                "air_damper_point": "Air Valve Position Command",
                "zone_621_control": False,
                "flow_spt_override_control": True,
                "units": "metric",
            },
        }

        self.device_mapping = {
            device["address"]: device for _, device in self.device_config.items()
        }

        # Set a default configuration to ensure that self.configure is called immediately to setup
        # the agent.
        self.vip.config.set_default("config", self.default_config)
        # Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(
            self.configure, actions=["NEW", "UPDATE"], pattern="config"
        )

    def configure(self, config_name, action, contents):
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.

        Is called every time the configuration in the store changes.
        """
        config = self.default_config.copy()
        config.update(contents)
        _log.info("[LBS Agent INFO] - ATTEMPTING CONFIG FILE LOAD!")

        try:
            """
            self.building_topic = str(config["building_topic"])

            self.dr_event_air_dampr_close_lvl = float(
                config["dr_event_air_dampr_close_lvl"]
            )

            self.vendors = list(config["vendors"])
            self.nested_group_map = dict(config["nested_group_map"])
            """
            pass

        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        _log.info(f"[LBS Agent INFO] - CONFIG FILE LOAD SUCCESS!")
        """
        _log.info(
            f"[LBS Agent INFO] - CONFIGS nested_group_map is {self.nested_group_map}"
        )
        """

    def _create_subscriptions(self, ahu_topic):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_publish callback
        """
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        self.vip.pubsub.subscribe(
            peer="pubsub", prefix=ahu_topic, callback=self._handle_publish
        )

    def _handle_got_lbs_message(self, peer, sender, bus, topic, headers, message):
        """
        Callback triggered by the subscription setup using the topic from the agent's config file
        """
        # This function is called whenever an openadr event is seen on the bus
        # message should be the adr event dict

        topic_str_split = topic.split("/")
        device = topic_str_split[3]

        # _log.info(f"[LBS Agent PubSub] - INCOMING LBS device: {device} message is: {message}")

        def vav_lookup(pubsub_address, devices):
            address_to_device = {
                device["address"]: device for device in devices.values()
            }
            device = address_to_device.get(pubsub_address)
            if device:
                point = device["flow_point"]

                # grab data from the message bus dictionary
                flow = message[0].get(point)

                if device["units"] == "metric":
                    flow = flow * 2.119

                device["data_storage"].append(flow)
                _log.info(
                    f"[LBS Agent PubSub] - VAV data stored success! {device['name']}"
                )

                if device["zone_621_control"]:
                    _log.info(
                        f"[LBS Agent PubSub] - 62.1 control hit for {device['name']}!"
                    )
                    self.handle_vav_box_(device, message, flow)

        if device == self.wifi_prefix:
            # _log.info(f"[LBS Agent PubSub] - LBS data stored success! {device}")
            self.handle_lbs_(message)

        elif device == self.ahu_prefix:
            dpr = message[0].get(self.ahu_oa_dpr_point)
            self.ahu_oa_dpr_cmd = dpr
            # _log.info(f"[LBS Agent PubSub] - AHU data stored success! {device}")

        else:
            vav_lookup(device, self.device_mapping)

    def handle_vav_box_(self, device, message, vav_flow):
        """
        "zone_621_control" : False,
        "flow_spt_override_control" : True,
        "units": "metric",
        """

        _now = get_aware_utc_now()
        last_scan_calc = abs(device["last_scan"] - _now).total_seconds()
        _log.info(f"[LBS Agent PubSub] - LAST SCAN CALC SECONDS is: {last_scan_calc}")

        # only make VAV box damper adjustments every 2 minutes
        if last_scan_calc < 120.0:
            return

        if not device["flow_spt_override_control"]:  # its air dpr control
            vav_str = f"slipstream_internal/slipstream_hq/25/DPR-O"
            vav_temp = message[0].get(device["zone_temp_point"])
            vav_temp_sp = message[0].get(device["zone_temp_spt_point"])
            vav_dpr = message[0].get(device["air_damper_point"])

            _log.info(f"[LBS Agent PubSub] - People Count is: {self.zone1_lv}")
            _log.info(f"[LBS Agent PubSub] - ZNT is: {vav_temp}")
            _log.info(f"[LBS Agent PubSub] - ZNT-SP is: {vav_temp_sp}")
            _log.info(f"[LBS Agent PubSub] - DPR is: {vav_dpr}")
            _log.info(f"[LBS Agent PubSub] - FLOW is: {vav_flow}")

            if vav_temp and vav_temp_sp is not None:
                znt_deviation_abs = abs(vav_temp - vav_temp_sp)
                _log.info(f"[LBS Agent PubSub] - ZNT ABS DEV is: {znt_deviation_abs}")

                # calculate a new VAV box flow setpoint
                flow_setpoint = self.calc_vav_flow_setpoint()
                _log.info(f"[LBS Agent PubSub] - Calculated SA-F: {flow_setpoint}")

                if flow_setpoint is None:
                    self.bacnet_release()
                    _log.info(f"[LBS Agent PubSub] - BACnet release called!")
                    _log.info(f"[LBS Agent PubSub] - Flow Setpoint Calc == None")

                if vav_flow > flow_setpoint:
                    flow_deviation = 1 - (flow_setpoint / vav_flow)

                else:
                    flow_deviation = 1 - (vav_flow / flow_setpoint)

                _log.info(f"[LBS Agent PubSub] - flow_deviation: {flow_deviation}")

                if flow_deviation < 0.2:
                    _log.info(
                        f"[LBS Agent PubSub] - flow_deviation is less than 20 percent! Skipping control!"
                    )
                    return

                # if the zone temp deviation is less than or equal to 3.5
                if znt_deviation_abs <= 3.5:
                    # CLOSE DAMPER 5 PERCENT TO MEET NEW CALC SETPOINT
                    if flow_setpoint < vav_flow:
                        # CLOSE the damper some
                        new_dpr_pos = vav_dpr - 1

                        _log.info(
                            f"[LBS Agent PubSub] - Calculated DPR-O - 1: {new_dpr_pos}"
                        )

                        if new_dpr_pos > 0:
                            self.bacnet_write(new_dpr_pos, vav_str)
                            _log.info(f"[LBS Agent PubSub] - BACnet write SUCCESS!")

                    # OPEN DAMPER 5 PERCENT TO MEET NEW CALC SETPOINT
                    elif flow_setpoint > vav_flow:
                        # OPEN the damper some
                        new_dpr_pos = vav_dpr + 1

                        _log.info(
                            f"[LBS Agent PubSub] - Calculated DPR-O + 1: {new_dpr_pos}"
                        )

                        if new_dpr_pos < 100:
                            self.bacnet_write(new_dpr_pos, vav_str)
                            _log.info(f"[LBS Agent PubSub] - BACnet write SUCCESS!")

                # if the zone temp falls out of dead band
                # BACnet release it to heat or cool
                elif znt_deviation_abs > 3.5 and self.bacnet_overrides_on_bas:
                    self.bacnet_release()
                    _log.info(f"[LBS Agent PubSub] - BACnet release called!")

                device["last_scan"] = get_aware_utc_now()

    def handle_lbs_(self, message):
        zone1_headcount = message[0].get("headcount-zone-1")  # "floor2_north" R&I area
        self.zone1_lv = zone1_headcount
        _log.info(
            f"[LBS Agent PubSub] - Zone 1 Head Count in floor2_north R&I area is: {self.zone1_lv}"
        )

        zone2_headcount = message[0].get(
            "headcount-zone-2"
        )  # "floor2_south" accounting area
        self.zone2_lv = zone2_headcount
        _log.info(f"[LBS Agent PubSub] - Zone 2 Head Count is: {self.zone2_lv}")

        zone3_headcount = message[0].get("headcount-zone-3")
        self.zone3_lv = zone3_headcount
        _log.info(f"[LBS Agent PubSub] - Zone 3 Head Count is: {self.zone3_lv}")

    def bacnet_write(self, cmd, vav_str):
        _log.info(f"[LBS Agent INFO] - bacnet_write GO!")

        start = datetime.now()
        end = start + timedelta(seconds=10)

        str_start = start.strftime("%Y-%m-%dT%H:%M:%S.%f")
        str_end = end.strftime("%Y-%m-%dT%H:%M:%S.%f")

        actuator_schedule_request = []
        actuator_schedule_request.append([vav_str, str_start, str_end])
        _log.info(
            f"[LBS Agent INFO] - bacnet_write actuator_schedule_request is {actuator_schedule_request}"
        )

        # use actuator agent to get all zone temperature setpoint data
        actuator_sched_req_result = self.vip.rpc.call(
            "platform.actuator",
            "request_new_schedule",
            self.core.identity,
            "my_schedule",
            "HIGH",
            actuator_schedule_request,
        ).get(timeout=90)

        write_to_bas = [(vav_str, cmd)]
        self.vip.rpc.call(
            "platform.actuator", "set_multiple_points", self.core.identity, write_to_bas
        ).get(timeout=300)

        self.bacnet_overrides_on_bas = True
        _log.info(f"[LBS Agent INFO] - WRITE SUCCESS")

    def bacnet_release(self):
        _log.info(f"[LBS Agent INFO] - BACnet Release GO!")

        start = datetime.now()
        end = start + timedelta(seconds=10)

        str_start = start.strftime("%Y-%m-%dT%H:%M:%S.%f")
        str_end = end.strftime("%Y-%m-%dT%H:%M:%S.%f")

        vav_str = "slipstream_internal/slipstream_hq/25/DPR-O"

        actuator_schedule_request = []
        actuator_schedule_request.append([vav_str, str_start, str_end])
        _log.info(
            f"[LBS Agent INFO] - bacnet_write actuator_schedule_request is {actuator_schedule_request}"
        )

        # use actuator agent to get all zone temperature setpoint data
        actuator_sched_req_result = self.vip.rpc.call(
            "platform.actuator",
            "request_new_schedule",
            self.core.identity,
            "my_schedule",
            "HIGH",
            actuator_schedule_request,
        ).get(timeout=90)

        write_to_bas = [(vav_str, None)]
        self.vip.rpc.call(
            "platform.actuator", "set_multiple_points", self.core.identity, write_to_bas
        ).get(timeout=300)

        self.bacnet_overrides_on_bas = False
        _log.info(f"[LBS Agent INFO] - BACnet Release SUCCESS!")

    def calc_vav_flow_setpoint(self):
        # CFM_setpoint = ((CFM/sqft * sqft + CFM/person * person_count) / EZ1) / PERCENT_OA

        if self.percent_oa != 0:
            setpoint = (
                (
                    self.office_per_sqft_cfm_req * self.zone_sqft_vav
                    + self.per_person_cfm_req * self.zone1_lv
                )
                / self.EZ1
                / self.percent_oa
            )

        else:
            setpoint = None

        _log.info(f"[LBS Agent INFO] - calc_vav_flow_setpoint INFO!")
        _log.info(
            f"[LBS Agent INFO] - self.office_per_sqft_cfm_req: {self.office_per_sqft_cfm_req}"
        )
        _log.info(f"[LBS Agent INFO] - self.zone_sqft_vav: {self.zone_sqft_vav}")
        _log.info(
            f"[LBS Agent INFO] - self.per_person_cfm_req: {self.per_person_cfm_req}"
        )
        _log.info(f"[LBS Agent INFO] - self.EZ1: {self.EZ1}")
        _log.info(f"[LBS Agent INFO] - self.percent_oa: {self.percent_oa}")
        _log.info(f"[LBS Agent INFO] - setpoint: {setpoint}")

        return setpoint

    def calculate_total_supply_flow(self):
        total_flow_temp = 0
        window_size = 5
        erv_design_cfm = 6400

        _log.info(f"[LBS Agent INFO] - calculate_total_supply_flow GO!")

        for key, vav_box in self.device_mapping.items():
            device = vav_box["name"]
            flow = vav_box["data_storage"]

            if flow == []:
                _log.info(f"[LBS Agent INFO] - EMPTY LIST DETECTED! On device {device}")

            else:
                try:
                    # calculate moving average of data insides lists
                    numbers_series = pd.Series(flow)
                    windows = numbers_series.rolling(window_size)
                    moving_averages = windows.mean()
                    moving_averages_list = moving_averages.tolist()
                    flow_as_moving_avg = moving_averages_list[window_size - 1 :][0]
                    _log.info(
                        f"[LBS Agent INFO] - {device} flow_as_moving_avg is {flow_as_moving_avg}"
                    )

                    total_flow_temp += flow_as_moving_avg

                except Exception as e:
                    _log.info(
                        f"[LBS Agent INFO] - Exception trying to compute moving average! - {e}"
                    )

                flow.clear()

        vav_sys_total_flow_pub = [{"vav_sys_total_flow": total_flow_temp}]

        """
        # publish to message bus
        self.vip.pubsub.publish(
            peer="pubsub",
            topic=self.calcs_pub_str,
            headers={headers.TIMESTAMP: format_timestamp(get_aware_utc_now())},
            message=f"TOTAL_AIR_FLOW/{total_flow_temp}",
        )
        """

        # publish to message bus
        self.vip.pubsub.publish(
            peer="pubsub",
            topic=self.calcs_pub_str,
            headers={headers.TIMESTAMP: format_timestamp(get_aware_utc_now())},
            message=vav_sys_total_flow_pub,
        )

        if total_flow_temp != 0:
            percent_oa = erv_design_cfm / total_flow_temp

        else:
            percent_oa = 0

        self.total_flow_temp = total_flow_temp
        self.percent_oa = percent_oa

        _log.info(f"[LBS Agent INFO] - total_flow is {self.total_flow_temp}!")
        _log.info(f"[LBS Agent INFO] - percent_oa is {self.percent_oa}!")
        _log.info(f"[LBS Agent INFO] - ahu_oa_dpr_cmd is {self.ahu_oa_dpr_cmd}!")

        ahu_oa_dpr_cmd_as_percent = self.ahu_oa_dpr_cmd / 100
        if ahu_oa_dpr_cmd_as_percent > self.percent_oa:
            _log.info(f"[LBS Agent INFO] - ahu_oa_dpr_cmd_as_percent > percent_oa!")
            self.percent_oa = ahu_oa_dpr_cmd_as_percent
            _log.info(f"[LBS Agent INFO] - percent_oa is now {self.percent_oa}!")

        percent_oa_pub = [{"ahu_percent_oa": percent_oa}]

        """
        # publish to message bus
        self.vip.pubsub.publish(
            peer="pubsub",
            topic=self.calcs_pub_str,
            headers={headers.TIMESTAMP: format_timestamp(get_aware_utc_now())},
            message=f"PERCENT_OA/{self.percent_oa}",
        )
        """

        # publish to message bus
        self.vip.pubsub.publish(
            peer="pubsub",
            topic=self.calcs_pub_str,
            headers={headers.TIMESTAMP: format_timestamp(get_aware_utc_now())},
            message=percent_oa_pub,
        )

    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):
        _log.info(f"[LBS Agent ONSTART] - onstart GO!")

        for device in self.device_mapping.values():
            device["data_storage"] = []
            device["last_scan"] = get_aware_utc_now()
            store_this_address = self.building_topic + device["address"] + "/all"
            self.pub_sub_subscriptions.append(store_this_address)

        wifi_str = self.building_topic + self.wifi_prefix + "/wifi/all"
        ahu_str = self.building_topic + self.ahu_prefix + "/all"

        self.pub_sub_subscriptions.append(wifi_str)
        self.pub_sub_subscriptions.append(ahu_str)

        for string in self.pub_sub_subscriptions:
            self.vip.pubsub.subscribe(
                peer="pubsub",
                prefix=string,
                callback=self._handle_got_lbs_message,
            )

            _log.info(f"[LBS Agent ONSTART] - Subrscribe to: {string}")

        self.core.periodic(300, self.calculate_total_supply_flow)
        _log.info(f"[LBS Agent ONSTART] - onstart DONE!")

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """

        _log.info(f"[LBS Agent ONSTOP] - onstop CALLED!!")
        self.bacnet_release()

        _log.info(f"[LBS Agent ONSTOP] - onstop SUCESS!!")

    @RPC.export
    def rpc_method(self, arg1, arg2, kwarg1=None, kwarg2=None):
        """
        RPC method

        May be called from another agent via self.core.rpc.call
        """
        pass


def main():
    """Main method called to start the agent."""
    utils.vip_main(LbsWifi, version=__version__)


if __name__ == "__main__":
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
