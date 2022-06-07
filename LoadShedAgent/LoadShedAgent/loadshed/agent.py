
"""
Agent documentation goes here. 
"""

__docformat__ = 'reStructuredText'

import logging, gevent, heapq, grequests
import sys
from datetime import timedelta as td, datetime as dt
from volttron.platform.agent.utils import format_timestamp, get_aware_utc_now
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
from volttron.platform.scheduling import cron
import random
from datetime import datetime, timezone, timedelta

from loadshed.helpers import HELPERS as f

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"



event = {
	"active_period": {
		"dstart": datetime(2022, 6, 6, 14, 30, 0, 0, tzinfo=timezone.utc),
		"duration": 120,
		"notification": "null",
		"ramp_up": "null",
		"recovery": "null",
		"tolerance": {
			"tolerate": {
				"startafter": "null"
			}
		}
	},
	"event_signals": [
		{
			"current_value": 2.0,
			"intervals": [
				{
					"duration": timedelta(minutes=30),
                    #"dtstart": datetime.now(timezone.utc),
                    "dtstart": datetime(2022, 6, 6, 14, 30, 0, 0, tzinfo=timezone.utc),
					"signal_payload": 1.0,
					"uid": 0
				}
			],
			"signal_id": "SIG_01",
			"signal_name": "SIMPLE",
			"signal_type": "level"
		}
	],
	"response_required": "always",
	"target_by_type": {
		"ven_id": [
			"slipstream-ven4"
		]
	},
	"targets": [
		{
			"ven_id": "slipstream-ven4"
		}
	]
}



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
        _log.debug(f'[Simple DR Agent INFO] - debug config {config}')
    except Exception:
        config = {}

    if not config:
        _log.debug("[Simple DR Agent INFO] - Using Agent defaults for starting configuration.")


    return Loadshed(**kwargs)
    


class Loadshed(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, **kwargs):
        super(Loadshed, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.default_config = {
        "building_topic": "slipstream_internal/slipstream_hq",

        "vendor1_bacnet_id_start": 1,
        "vendor1_bacnet_id_end": 100,
        "vendor1_zonetemp_topic": "ZN-T",
        "vendor1_zonetemp_setpoint_topic": "ZN-SP",
        "vendor1_occ_topic": "OCC-SCHEDULE",
        "vendor1_reheat_valves_topic": "HTG-O",

        "vendor2_bacnet_id_start": 10000,
        "vendor2_bacnet_id_end": 12000,
        "vendor2_zonetemp_topic": "Space Temperature Local",
        "vendor2_zonetemp_setpoint_topic": "Space Temperature Setpoint BAS",
        "vendor2_occ_topic": "Occupancy Request",
        "vendor2_reheat_valves_topic": "None",

        "dr_event_zntsp_adjust_up": ".30",
        "dr_event_zntsp_adjust_down": "-.30",

        }


        self.building_topic = str(self.default_config["building_topic"])

        self.vendor1_bacnet_id_start: int(self.default_config["vendor1_bacnet_id_start"])
        self.vendor1_bacnet_id_end: int(self.default_config["vendor1_bacnet_id_end"])
        self.vendor1_zonetemp_topic = str(self.default_config["vendor1_zonetemp_topic"])
        self.vendor1_zonetemp_setpoint_topic = str(self.default_config["vendor1_zonetemp_setpoint_topic"])
        self.vendor1_occ_topic = str(self.default_config["vendor1_occ_topic"])
        self.vendor1_reheat_valves_topic = str(self.default_config["vendor1_reheat_valves_topic"])

        self.vendor2_bacnet_id_start = int(self.default_config["vendor2_bacnet_id_start"])
        self.vendor2_bacnet_id_end = int(self.default_config["vendor2_bacnet_id_end"])
        self.vendor2_zonetemp_topic = str(self.default_config["vendor2_zonetemp_topic"])
        self.vendor2_zonetemp_setpoint_topic = str(self.default_config["vendor2_zonetemp_setpoint_topic"])
        self.vendor2_occ_topic = str(self.default_config["vendor2_occ_topic"])
        self.vendor2_reheat_valves_topic = str(self.default_config["vendor2_reheat_valves_topic"])

        self.dr_event_zntsp_adjust_up = float(self.default_config["dr_event_zntsp_adjust_up"])
        self.dr_event_zntsp_adjust_down = float(self.default_config["dr_event_zntsp_adjust_down"])

        self.nested_group_map = {}

        self.agent_id = "loadshedagent"

        self.bacnet_releases_complete = False
        self.bacnet_overrides_complete = False

        self.adr_start = None
        self.adr_payload_value = None
        self.adr_duration = None
        self.adr_event_status = False



        # Set a default configuration to ensure that self.configure is called immediately to setup
        # the agent.
        self.vip.config.set_default("config", self.default_config)
        # Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")

    def configure(self, config_name, action, contents):
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.

        Is called every time the configuration in the store changes.
        """
        config = self.default_config.copy()
        config.update(contents)
        _log.debug("[Simple DR Agent INFO] - ATTEMPTING CONFIG FILE LOAD!")

        try:
            building_topic = str(config["building_topic"])

            self.vendor1_bacnet_id_start: int(config["vendor1_bacnet_id_start"])
            self.vendor1_bacnet_id_end: int(config["vendor1_bacnet_id_end"])
            self.vendor1_zonetemp_topic = str(config["vendor1_zonetemp_topic"])
            self.vendor1_zonetemp_setpoint_topic = str(config["vendor1_zonetemp_setpoint_topic"])
            self.vendor1_occ_topic = str(config["vendor1_occ_topic"])
            self.vendor1_reheat_valves_topic = str(config["vendor1_reheat_valves_topic"])

            self.vendor2_bacnet_id_start = int(config["vendor2_bacnet_id_start"])
            self.vendor2_bacnet_id_end = int(config["vendor2_bacnet_id_end"])
            self.vendor2_zonetemp_topic = str(config["vendor2_zonetemp_topic"])
            self.vendor2_zonetemp_setpoint_topic = str(config["vendor2_zonetemp_setpoint_topic"])
            self.vendor2_occ_topic = str(config["vendor2_occ_topic"])
            self.vendor2_reheat_valves_topic = str(config["vendor2_reheat_valves_topic"])

            self.dr_event_zntsp_adjust_up = float(config["dr_event_zntsp_adjust_up"])
            self.dr_event_zntsp_adjust_down = float(config["dr_event_zntsp_adjust_down"])

            self.nested_group_map = {}
         
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        _log.debug(f'[Simple DR Agent INFO] - CONFIG FILE LOAD SUCCESS!')
        _log.debug(f'[Simple DR Agent INFO] - CONFIGS SET SUCCESS!')




    def _create_subscriptions(self, ahu_topic):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_publish callback
        """
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix=ahu_topic,
                                  callback=self._handle_publish)



    def _handle_publish(self, peer, sender, bus, ahu_topic, headers, message):
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
        # Just write something to the logs so that we can see our success
        _log.debug("[Simple DR Agent INFO] - Device {} Publish: {}".format(self.ahu_topic, message))



    def process_adr_event(self,event):
        signal = event['event_signals'][0]
        intervals = signal['intervals']

        _log.debug(f"[Simple DR Agent INFO] - process_adr_event called")

        for interval in intervals:
            self.adr_start = interval['dtstart']
            self.adr_payload_value = interval['signal_payload']
            self.adr_duration = interval['duration']
           
        _log.debug(f"[Simple DR Agent INFO] - open ADR process of signal sucess!")
        _log.debug(f"[Simple DR Agent INFO] - adr_start is {self.adr_start}")
        _log.debug(f"[Simple DR Agent INFO] - adr_payload_value {self.adr_payload_value}")
        _log.debug(f"[Simple DR Agent INFO] - adr_duration {self.adr_duration}")

        self.adr_event_status = f.event_checkr(self,self.adr_start,self.adr_duration)
        _log.debug(f"[Simple DR Agent INFO] - adr_event_status {self.adr_event_status}")


    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):
        default_config = self.default_config.copy()
        _log.debug(f"[Simple DR Agent INFO] - onstart config: {default_config}")


        # dummy event until real event comes in via open ADR VEN agent
        self.process_adr_event(event)
        _log.debug(f"[Simple DR Agent INFO] - process_adr_event hit")
        
        # continously check for event status
        while f.event_checkr(self,self.adr_start,self.adr_duration) == True:

            if self.bacnet_overrides_complete == False:
                _log.debug(f"[Simple DR Agent INFO] - Demand Response Event True!!!")
                _log.debug(f'[Simple DR Agent INFO] - bacnet_override_go GO!!!!')
                f.bacnet_override_go(self)
                self.bacnet_overrides_complete = True

        else:

            # after dr event expires we should hit this if statement to release BAS
            if self.bacnet_releases_complete == False and self.bacnet_overrides_complete == True:
                _log.debug(f'[Simple DR Agent INFO] - bacnet_release_go GO!!!!')
                f.bacnet_release_go(self)
                self.bacnet_releases_complete = True
                _log.debug(f'[Simple DR Agent INFO] - bacnet_release_go SUCCESS')
                _log.debug(f'[Simple DR Agent INFO] - self.bacnet_releases_complete is {self.bacnet_releases_complete}')
                _log.debug(f'[Simple DR Agent INFO] - self.bacnet_overrides_complete is {self.bacnet_overrides_complete}')


            # after dr event expires if release and override complete, reset params
            elif self.bacnet_releases_complete == True and self.bacnet_overrides_complete == True:
                self.bacnet_releases_complete = False
                self.bacnet_overrides_complete = False
                _log.debug(f'[Simple DR Agent INFO] -  params all RESET SUCCESS!')
                _log.debug(f'[Simple DR Agent INFO] -  self.bacnet_releases_complete is {self.bacnet_releases_complete}')
                _log.debug(f'[Simple DR Agent INFO] -  self.bacnet_overrides_complete is {self.bacnet_overrides_complete}')

            else:
                pass


    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        _log.debug(f'[Simple DR Agent INFO] - onstop RELEASE BACnet')

        #self.bacnet_release_go()

        _log.debug(f'[Simple DR Agent INFO] - onstop BACnet RELEASE success!')




    @RPC.export
    def rpc_method(self, arg1, arg2, kwarg1=None, kwarg2=None):
        """
        RPC method

        May be called from another agent via self.core.rpc.call
        """
        pass



def main():
    """Main method called to start the agent."""

    try:
        utils.vip_main(load_me, version=__version__)
    except Exception as exception:
        _log.exception("unhandled exception")
        _log.error(repr(exception))




if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass

