"""
Agent documentation goes here.
"""

__docformat__ = "reStructuredText"

import logging
import sys
import operator
import pandas as pd
import numpy as np
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
from volttron.platform.messaging import topics, headers

from faultmachine import FaultConditionOne

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


def faultmachine(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Faultmachine
    :rtype: Faultmachine
    """
    try:
        config = utils.load_config(config_path)
        _log.debug(f"[G36 Agent INFO] -  config Load SUCCESS")
    except Exception:
        _log.debug(f"[G36 Agent INFO] -  config Load FAIL")

        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    return Faultmachine(**kwargs)


class Faultmachine(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, setting1=1, setting2="some/random/topic", **kwargs):
        super(Faultmachine, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.default_config = {
            "ahu_instance_id": "1100",
            "building_topic": "slipstream_internal/slipstream_hq",
            "duct_static_setpoint": "Duct Static Pressure Setpoint Active",
            "duct_static": "Duct Static Pressure Local",
            "vfd_speed": "Supply Fan Speed Command",
        }

        ahu_instance_id = str(self.default_config["ahu_instance_id"])
        building_topic = str(self.default_config["building_topic"])
        duct_static_setpoint = str(self.default_config["duct_static_setpoint"])
        duct_static = str(self.default_config["duct_static"])
        vfd_speed = str(self.default_config["vfd_speed"])

        self.ahu_instance_id = ahu_instance_id
        self.building_topic = building_topic
        self.duct_static_setpoint = duct_static_setpoint
        self.duct_static = duct_static
        self.vfd_speed = vfd_speed

        self.nested_group_map = {"air_handlers": {"AHU1": "1100"}}

        self.ahu_subscription = "/".join(
            ["devices", self.building_topic, self.ahu_instance_id]
        )
        self.duct_static_setpoint_topic = "/".join(
            [self.building_topic, self.ahu_instance_id, self.duct_static_setpoint]
        )
        self.duct_static_topic = "/".join(
            [self.building_topic, self.ahu_instance_id, self.duct_static]
        )
        self.vfd_speed_topic = "/".join(
            [self.building_topic, self.ahu_instance_id, self.vfd_speed]
        )

        self.duct_static_setpoint_data = []
        self.duct_static_data = []
        self.vfd_speed_data = []

        # G36 FC1 params for the FDD algorithm
        self.vfd_speed_percent_err_thres = 0.05
        self.duct_static_inches_err_thres = 0.99
        self.vfd_speed_percent_max = 0.1

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

        _log.debug("[G36 Agent INFO] - Configuring Agent")

        try:
            ahu_instance_id = str(config["ahu_instance_id"])
            building_topic = str(config["building_topic"])
            duct_static_setpoint = str(config["duct_static_setpoint"])
            duct_static = str(config["duct_static"])
            vfd_speed = str(config["vfd_speed"])

        except ValueError as e:
            _log.error(
                "[G36 Agent INFO] - ERROR PROCESSING CONFIGURATION: {}".format(e)
            )
            return

        self.ahu_instance_id = ahu_instance_id
        self.building_topic = building_topic
        self.duct_static_setpoint = duct_static_setpoint
        self.duct_static = duct_static
        self.vfd_speed = vfd_speed

        self.duct_static_setpoint_topic = "/".join(
            [self.building_topic, self.ahu_instance_id, self.duct_static_setpoint]
        )
        self.duct_static_topic = "/".join(
            [self.building_topic, self.ahu_instance_id, self.duct_static]
        )
        self.vfd_speed_topic = "/".join(
            [self.building_topic, self.ahu_instance_id, self.vfd_speed]
        )

        _log.debug("[G36 Agent INFO] - Configs Set Success")

    def _create_subscriptions(self, topics):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_publish callback
        """
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        _log.debug(f"[G36 Agent INFO] -  _create_subscriptions {topics}")
        self.vip.pubsub.subscribe(
            peer="pubsub", prefix=topics, callback=self._handle_publish
        )

    def _handle_publish(self, peer, sender, bus, topic, headers, message):
        """
        When we recieve an update from our all publish subscription, log something so we can see that we are
        successfully scraping CSV points with the Platform Driver
        :param peer: unused
        :param sender: unused
        :param bus: unused
        :param topic: unused
        :param headers: unused
        :param message: "All" messaged published by the Platform Driver for the CSV Driver containing values for all
        registers on the device
        """

        # _log.info(f"[G36 Agent INFO] - INCOMING AHU Data: {message[0]}")

        topic = topic.strip("/all")
        _log.debug(f"*** [G36 Agent INFO] *** topic_formatted {topic}")
        _log.debug(f"*** [G36 Agent INFO] *** message[0] is {message[0]}")

        duct_static_setpoint_ = message[0].get(self.duct_static_setpoint)
        _log.info(
            f"[G36 Agent INFO] - Duct Static Pressure Setpoint is: {duct_static_setpoint_}"
        )
        self.duct_static_setpoint_data.append(duct_static_setpoint_)

        duct_static_ = message[0].get(self.duct_static)
        _log.info(f"[G36 Agent INFO] - Duct Static Pressure is: {duct_static_}")
        self.vfd_speed_data.append(duct_static_)

        vfd_speed_ = message[0].get(self.vfd_speed)
        _log.info(f"[G36 Agent INFO] - AHU Fan VFD Speed is: {vfd_speed_}")
        self.vfd_speed_data.append(vfd_speed_)

    # if enough data exists run faults and then clear lists at the end
    # G36 states 1 minute data on 5 minute rolling averages
    @Core.periodic(10)
    def fault_checker(self):
        _log.debug(f"[G36 Agent INFO] - fault_checker GO!: \
            {len(self.duct_static_setpoint_data)}")

        if len(self.duct_static_setpoint_data) == 0:
            _log.debug(
                f"[G36 Agent INFO] - Not enough accumilated data to run fault checker")
            return

        elif len(self.duct_static_setpoint_data) >= 5:
            _log.debug(f"[G36 Agent INFO] - Running Fault Machine!!!")

            df = pd.DataFrame(
                list(
                    zip(
                        self.duct_static_data,
                        self.duct_static_setpoint_data,
                        self.vfd_speed_data,
                    )
                ),
                columns=["duct_static", "duct_static_setpoint", "supply_vfd_speed"],
            )
            _log.debug(f"[G36 Agent INFO] - NOT rolling df is {df}")

            df = df.rolling(window=5).mean()
            _log.debug(f"[G36 Agent INFO] - rolling df is {df}")

            df_lastrow = df.iloc[-1:]
            _log.debug(f"[G36 Agent INFO] - df last row is {df_lastrow}")

            _fc1 = FaultConditionOne(
                self.vfd_speed_percent_err_thres,
                self.duct_static_inches_err_thres,
                self.vfd_speed_percent_max,
                "duct_static",
                "supply_vfd_speed",
                "duct_static_setpoint",
            )

            _log.debug(f"[G36 Agent INFO] - fault_condition_one {_fc1}")

            self.duct_static_setpoint_data.clear()
            self.duct_static_data.clear()
            self.vfd_speed_data.clear()

            """
            #publish to message bus
            self.vip.pubsub.publish(
                peer="pubsub",
                topic=f"analysis",
                headers={
                    headers.TIMESTAMP: utils.format_timestamp(utils.get_aware_utc_now())
                },
                message=f"FAULTS_FC1/{self.ahu_instance_id}/{int(fdd_check)}",
            )
            """

    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):
        """
        This is method is called once the Agent has successfully connected to the platform.
        This is a good place to setup subscriptions if they are not dynamic or
        do any other startup activities that require a connection to the message bus.
        Called after any configurations methods that are called at startup.

        Usually not needed if using the configuration store.
        prefix="devices/slipstream_internal/slipstream_hq/1100/"
        """

        subscription_prefix = f"devices/{self.building_topic}/{self.ahu_instance_id}/"
        _log.debug(f"[G36 Agent INFO] - subscribe to: {subscription_prefix}")

        self.vip.pubsub.subscribe(
            peer="pubsub",
            prefix=subscription_prefix,
            callback=self._handle_publish,
        )

        #self.core.periodic(10, self.fault_checker)

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        pass

    @RPC.export
    def rpc_method(self, arg1, arg2, kwarg1=None, kwarg2=None):
        """
        RPC method

        May be called from another agent via self.core.rpc.call
        """
        return self.setting1 + arg1 - arg2


def main():
    """Main method called to start the agent."""
    utils.vip_main(faultmachine, version=__version__)


if __name__ == "__main__":
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
