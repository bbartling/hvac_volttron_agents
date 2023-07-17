"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys

from volttron.platform.agent.utils import format_timestamp, get_aware_utc_now
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC

from datetime import timedelta as td


_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"



def rtuloadshed(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Rtuloadshed
    :rtype: Rtuloadshed
    """
    try:
        global config
        config = utils.load_config(config_path)
        _log.info(f'[RTU Load Shed INFO] - debug config {config}')
    except Exception:
        config = {}

    if not config:
        _log.info("[RTU Load Shed INFO] - Using Agent defaults for starting configuration.")


    return Rtuloadshed(**kwargs)


class Rtuloadshed(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self,**kwargs):
        super(Rtuloadshed, self).__init__(**kwargs)
        _log.debug("[RTU Load Shed INFO] vip_identity: " + self.core.identity)

        self.default_config = {
        "rtu_topic": "devices/slipstream_internal/slipstream_hq/1100/all",
        "adr_gateway_topic": "devices/3056672/all", #3056672
        "electric_meter_topic": "devices/slipstream_internal/slipstream_hq/5231/all",
        "electric_meter_point": "REGCHG p_mdp_panel_total",
        "rtu_fan_point" : "Supply Fan Speed Command",
        "clg_compressors":[
            "Compressor 1 Command",
            "Compressor 2 Command",
            "Compressor 3 Command",
            "Compressor 4 Command"
            ]
        }


        self.rtu_topic = str(self.default_config["rtu_topic"])
        self.clg_compressors = str(self.default_config["clg_compressors"])
        self.adr_gateway_topic = str(self.default_config["adr_gateway_topic"])
        self.electric_meter_topic = str(self.default_config["electric_meter_topic"])
        self.electric_meter_point = str(self.default_config["electric_meter_point"])
        self.rtu_fan_point = str(self.default_config["rtu_fan_point"])
        self.clg_compressors_running = 0
        self.bacnet_override_go_running = False
        self.electric_meter_value = 0
        self.rtu_fan_value = 0
        self.bacnet_writes_are_running = False
        self.bacnet_writes_applied = False
        
        # this data structure is used for bacnet_release_go()
        self.log_of_points_written = []

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

        _log.debug("Configuring Agent")

        try:
            self.rtu_topic = str(config["rtu_topic"])
            self.clg_compressors = str(config["clg_compressors"])
            self.adr_gateway_topic = str(config["adr_gateway_topic"])
            self.electric_meter_topic = str(config["electric_meter_topic"])
            self.electric_meter_point = str(config["electric_meter_point"])
            self.rtu_fan_point = str(config["rtu_fan_point"])

        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        _log.info(f'[RTU Load Shed INFO] - CONFIG FILE LOAD SUCCESS!')


    def _create_subscriptions(self, topic):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_publish callback
        """
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix=topic,
                                  callback=self._handle_publish)

    def _handle_publish(self, peer, sender, bus, topic, headers, message):
        """
        Callback triggered by the subscription setup using the topic from the agent's config file
        """
        log_prefix = "[RTU Load Shed Handle Publish]"
        msg_data = message[0]

        if topic == self.electric_meter_topic:
            self.electric_meter_value = msg_data.get(self.electric_meter_point)
            _log.info(f"{log_prefix} - Electric meter data is: {self.electric_meter_value}")
                
        elif topic == self.rtu_topic:
            compressor_status = {}
            clg_compressors_calc = 0  # Reset the count of running compressors
            self.rtu_fan_value = msg_data.get(self.rtu_fan_point)
            
            for key in msg_data.keys():
                if key in self.clg_compressors:
                    status = msg_data[key]
                    compressor_status[key] = status
                    if status == 1:  # If the compressor is running
                        clg_compressors_calc += 1  # Increment the count of running compressors

            self.clg_compressors_running = clg_compressors_calc     
            _log.info(f"{log_prefix} - INCOMING RTU msg: {topic} Compressor status: {compressor_status}")
            _log.info(f"{log_prefix} - Number of compressors running: {self.clg_compressors_running}")
            _log.info(f"{log_prefix} - Fan Speed is: {self.rtu_fan_value}")

    def bacnet_write_load_shed_go(self):
        log_prefix = '[RTU Load Shed GO INFO]'
        
        if self.bacnet_writes_are_running or self.bacnet_writes_applied:
            _log.info(f'{log_prefix} - self.bacnet_writes_are_running or self.bacnet_writes_applied success')
            return
        
        _log.info(f'{log_prefix} - clg compressors: {self.clg_compressors_running}')
        if self.clg_compressors_running <= 2:
            _log.info(f'{log_prefix} - not enough cooling running to need writes')
            return

        self.bacnet_writes_are_running = True
        
        _now = get_aware_utc_now()
        str_start = format_timestamp(_now)
        _end = _now + td(seconds=10)
        str_end = format_timestamp(_end)

        rtu_address = "slipstream_internal/slipstream_hq/1100"
        actuator_schedule_request = [[rtu_address, str_start, str_end]]

        # use actuator agent to get all zone temperature setpoint data
        self.vip.rpc.call('platform.actuator', 
                        'request_new_schedule', 
                        self.core.identity, 
                        'meter_write_val', 
                        'HIGH', 
                        actuator_schedule_request).get(timeout=90)

        write_to_rtu = []
        
        compressor3 = f"slipstream_internal/slipstream_hq/1100/Compressor 3 Command"
        write_to_rtu.append((compressor3, 0))
        
        compressor4 = f"slipstream_internal/slipstream_hq/1100/Compressor 4 Command"
        write_to_rtu.append((compressor4, 0))
            
        fanspeed = f"slipstream_internal/slipstream_hq/1100/Supply Fan Speed Command"
        write_to_rtu.append((fanspeed, 40.0))
        
        self.vip.rpc.call('platform.actuator',
                        'set_multiple_points', 
                        self.core.identity, 
                        write_to_rtu).get(timeout=300)
                   
        _log.info(f'{log_prefix} - bacnet_write_load_shed_go success')

        self.bacnet_writes_are_running = False
        self.bacnet_writes_applied = True

    def bacnet_release_load_shed_go(self):
        log_prefix = '[RTU Load Shed Release INFO]'
        
        if self.bacnet_writes_are_running or not self.bacnet_writes_applied:
            _log.info(f'{log_prefix} - self.bacnet_writes_are_running or not self.bacnet_writes_applied success')
            return
        
        self.bacnet_writes_are_running = True

        _now = get_aware_utc_now()
        str_start = format_timestamp(_now)
        _end = _now + td(seconds=10)
        str_end = format_timestamp(_end)

        rtu_address = "slipstream_internal/slipstream_hq/1100"
        actuator_schedule_request = [[rtu_address, str_start, str_end]]

        # use actuator agent to get all zone temperature setpoint data
        self.vip.rpc.call('platform.actuator', 
                        'request_new_schedule', 
                        self.core.identity, 
                        'meter_write_val', 
                        'HIGH', 
                        actuator_schedule_request).get(timeout=90)

        write_to_rtu = []
        
        compressor3 = f"slipstream_internal/slipstream_hq/1100/Compressor 3 Command"
        write_to_rtu.append((compressor3, None))
        
        compressor4 = f"slipstream_internal/slipstream_hq/1100/Compressor 4 Command"
        write_to_rtu.append((compressor4, None))
            
        fanspeed = f"slipstream_internal/slipstream_hq/1100/Supply Fan Speed Command"
        write_to_rtu.append((fanspeed, None))
        
        self.vip.rpc.call('platform.actuator',
                        'set_multiple_points', 
                        self.core.identity, 
                        write_to_rtu).get(timeout=300)
                   
        _log.info(f'{log_prefix} - bacnet_release_load_shed_go success')
        
        self.bacnet_writes_are_running = False
        self.bacnet_writes_applied = False
        
    def check_dr_signal(self):
        log_prefix = '[RTU Load Shed Check Dr Sig INFO]'

        _now = get_aware_utc_now()
        str_start = format_timestamp(_now)
        _end = _now + td(seconds=10)
        str_end = format_timestamp(_end)

        device = "3056672"
        actuator_schedule_request = [[device, str_start, str_end]]

        # use actuator agent to get all adr_gateway_data data
        self.vip.rpc.call('platform.actuator', 
                        'request_new_schedule', 
                        self.core.identity, 
                        'meter_write_val', 
                        'HIGH', 
                        actuator_schedule_request).get(timeout=90)

        adr_gateway_data = self.vip.rpc.call('platform.actuator',
                        'scrape_all', 
                        #self.core.identity, 
                        device
                        ).get(timeout=300)    
                   
        _log.info(f'{log_prefix} - adr_gateway_data {adr_gateway_data}')
        #{'power-level': 0.0, 'openadr-server-connection-status': 1, 'demand-response-level': 0.0}
        
        dr_level = adr_gateway_data.get('demand-response-level')
        power_level = adr_gateway_data.get('power-level')
        server_connection_status = adr_gateway_data.get('openadr-server-connection-status')
        _log.info(f"{log_prefix} - INCOMING ADR dr_level: {dr_level} power_level is: {power_level} server_connection_status is: {server_connection_status}")

        if dr_level > 0.0:
            # load shed
            self.bacnet_write_load_shed_go()
        else:
            # release load shed
            self.bacnet_release_load_shed_go()

    def bacnet_write_meter_val(self):
        log_prefix = '[RTU Load Shed Meter Write INFO]'
        
        _log.info(f'{log_prefix} - bacnet_write_meter_val: {self.electric_meter_value}')

        _now = get_aware_utc_now()
        str_start = format_timestamp(_now)
        _end = _now + td(seconds=10)
        str_end = format_timestamp(_end)

        device = "3056672"
        actuator_schedule_request = [[device, str_start, str_end]]

        # use actuator agent to get all zone temperature setpoint data
        self.vip.rpc.call('platform.actuator', 
                        'request_new_schedule', 
                        self.core.identity, 
                        'meter_write_val', 
                        'HIGH', 
                        actuator_schedule_request).get(timeout=90)

        meter_topic = "3056672/power-level"
        self.vip.rpc.call('platform.actuator',
                        'set_point', 
                        self.core.identity, 
                        meter_topic,
                        self.electric_meter_value
                        ).get(timeout=300)    
                   
        _log.info(f'{log_prefix} - bacnet_write_meter_val success')
        

    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):
        log_prefix = '[RTU Load Shed Onstart INFO]'

        _log.info(f"{log_prefix} - onstart GO!")

        self.vip.pubsub.subscribe(
            peer="pubsub",
            prefix=self.adr_gateway_topic,
            callback=self._handle_publish,
        )
        _log.info(f"{log_prefix} - subscribed to: {self.adr_gateway_topic}")
        
        self.vip.pubsub.subscribe(
            peer="pubsub",
            prefix=self.rtu_topic,
            callback=self._handle_publish,
        )
        _log.info(f"{log_prefix} - subscribed to: {self.rtu_topic}")
        
        self.vip.pubsub.subscribe(
            peer="pubsub",
            prefix=self.electric_meter_topic,
            callback=self._handle_publish,
        )
        _log.info(f"{log_prefix} - subscribed to: {self.electric_meter_topic}")

        self.core.periodic(60, self.bacnet_write_meter_val)
        self.core.periodic(60, self.check_dr_signal)
        _log.info(f"{log_prefix} - onstart Done!") 


    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        log_prefix = '[RTU Load Shed Onstop INFO]'
        self.bacnet_release_load_shed_go()
        _log.info(f"{log_prefix} - onstop Done!")


def main():
    """Main method called to start the agent."""
    utils.vip_main(rtuloadshed, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
