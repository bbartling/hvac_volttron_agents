
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


_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


def load_me(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Setteroccvav
    :rtype: Setteroccvav
    """
    try:
        global config
        config = utils.load_config(config_path)
        _log.debug(f'*** [INFO] *** - debug config {config}')
    except Exception:
        config = {}

    if not config:
        _log.debug("Using Agent defaults for starting configuration.")


    return Setteroccvav(**kwargs)
    


class Setteroccvav(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, **kwargs):
        super(Setteroccvav, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)


        self.default_config = {

        "url": "http://10.200.200.224:5000/event-state/charmany"

        }


        url = str(self.default_config["url"])
        self.url = url
        _log.debug(f'*** [SIG CHECKER Agent INFO] *** -  DEFAULT CONFIG LOAD SUCCESS!')
        self.agent_id = "dr_event_setpoint_adj_agent"



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

        _log.debug("*** [SIG CHECKER Agent INFO] *** - ATTEMPTING CONFIG FILE LOAD!")



        try:

            url = str(config["url"])
         
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return


        _log.debug(f'*** [SIG CHECKER Agent INFO] *** -  CONFIG FILE LOAD SUCCESS!')

        self.url = url
        _log.debug(f'*** [SIG CHECKER Agent INFO] *** -  CONFIGS SET SUCCESS!')


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
        _log.debug("*** [Handle Pub Sub INFO] *** - Device {} Publish: {}".format(self.ahu_topic, message))


    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):
        self.core.periodic(60, self.dr_signal_checker)
        _log.debug(f'*** [SIG CHECKER Agent INFO] *** -  AGENT ONSTART CALLED SUCCESS!')


    def dr_signal_checker(self):

        try:
            requests = (grequests.get(self.url),)
            result, = grequests.map(requests)
            contents = result.json()
            _log.debug(f"Flask App API contents: {contents}")
            _log.debug(f"Flask App API SUCCESS")
            sig_payload = contents["current_state"]

        except Exception as error:
            _log.debug(f"*** [SIG CHECKER Agent INFO] *** - Error trying Flask App API {error}")
            _log.debug(f"*** [SIG CHECKER Agent INFO] *** - RESORTING TO NO DEMAND RESPONSE EVENT")
            sig_payload = 0

        _log.debug(f'*** [SIG CHECKER Agent INFO] *** - signal_payload from Flask App is {sig_payload}!')




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

