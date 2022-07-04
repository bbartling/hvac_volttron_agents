"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys

from volttron.platform.agent.utils import format_timestamp, get_aware_utc_now
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC

from datetime import timedelta as td, datetime as dt, timezone as tz


_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


DUMMY_EVENT = {
	"active_period": {
		"dstart": dt(2022, 6, 6, 14, 30, 0, 0, tzinfo=tz.utc), # not used?
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
					"duration": td(minutes=3),
                    "dtstart": dt.now(tz.utc) + td(seconds=10),
                    #"dtstart": dt(2022, 6, 22, 19, 0, tzinfo=tz.utc),
					"signal_payload": 2,
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

        "building_topic": "slipstream_internal/slipstream_hq",

        "nested_group_map" : {
            "rtus" : {
                "device_address": "1100",
                "clg_compressor_topic":[
                    "Compressor 1 Command",
                    "Compressor 2 Command",
                    "Compressor 3 Command",
                    "Compressor 4 Command"
                    ]
                }
            }
        }


        self.building_topic = str(self.default_config["building_topic"])
        self.nested_group_map = dict(self.default_config["nested_group_map"])

        self.bacnet_releases_complete = False
        self.bacnet_override_error_str = ""
        self.bacnet_override_error = False

        self.adr_start = None
        self.adr_payload_value = None
        self.adr_duration = None
        self.adr_event_ends = None

        self.until_start_time_seconds = None
        self.until_start_time_minutes = None
        self.until_start_time_hours = None

        self.until_end_time_seconds = None
        self.until_end_time_minutes = None
        self.until_end_time_hours = None

        self.event_checkr_isrunning = False
        self.last_bacnet_override_go_time = get_aware_utc_now()
        self.bas_points_that_are_written = []
        self.last_go_around_clg_running = 0

        self.last_adr_event_status_bool = False
        self.last_adr_event_date = None
        self.last_adr_event_status_string = ""


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
            self.building_topic = str(config["building_topic"])
            self.nested_group_map = dict(config["nested_group_map"])

        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        _log.info(f'[RTU Load Shed INFO] - CONFIG FILE LOAD SUCCESS!')
        _log.info(f'[RTU Load Shed INFO] - CONFIGS nested_group_map is {self.nested_group_map}')



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
        pass



    def bacnet_override_go(self):

        # if its the first go around
        if self.last_bacnet_override_go_time == None:
            self.last_bacnet_override_go_time = get_aware_utc_now()
            return

        _now = get_aware_utc_now()

        total_seconds = (_now - self.last_bacnet_override_go_time).total_seconds()
        _log.info(f"[RTU Load Shed INFO] - bacnet_override_go total_seconds: {total_seconds}")

        # only check cooling compressors every 60 seconds
        if total_seconds < 60:
            return

        _log.info(f"[RTU Load Shed INFO] - bacnet_override_go called to check clg compressors!")

        # create start and end timestamps for actuator agent scheduling
        str_start = format_timestamp(_now)
        _end = _now + td(seconds=10)
        str_end = format_timestamp(_end)


        actuator_schedule_request = []
        for device in self.nested_group_map.values():
            bacnet_address = device["device_address"]
            device = '/'.join([self.building_topic, str(bacnet_address)])
            actuator_schedule_request.append([device, str_start, str_end])

        _log.info(f'[RTU Load Shed INFO] - bacnet_override_go actuator_schedule_request is {actuator_schedule_request}')


        # use actuator agent to get all zone temperature setpoint data
        actuator_sched_req_result = self.vip.rpc.call('platform.actuator', 
                                                    'request_new_schedule', 
                                                    self.core.identity, 
                                                    'my_schedule', 
                                                    'HIGH', 
                                                    actuator_schedule_request).get(timeout=90)

        _log.info(f'[RTU Load Shed INFO] - bacnet_override_go actuator_sched_req_result is {actuator_sched_req_result}')


        actuator_get_this_data = []
        for device in self.nested_group_map.values():
            bacnet_address = device["device_address"]
            device_address = '/'.join([self.building_topic, str(bacnet_address)])

            # loop through cooling commands
            for clg_cmd in device['clg_compressor_topic']:
                device_and_point = '/'.join([device_address, clg_cmd])
                actuator_get_this_data.append(device_and_point)        


        clg_compressor_data = self.vip.rpc.call('platform.actuator', 
                                            'get_multiple_points', 
                                            actuator_get_this_data).get(timeout=300)

        _log.info(f'[RTU Load Shed INFO] - bacnet_override_go clg_compressor_data is {clg_compressor_data}')


        '''
        loop through data recieved back from actuator agent of zone setpoints
        create a new data structure and add the adjustment value to the zone setpoints
        use this data structure to write back to the BAS via the actuator agent
        also add to the data structure reheat coils to override closed which
        will prevent the vav box from going into a heat mode when the zone
        setpoints are adjusted upwards
        '''

        # append a new data structure to BACnet write
        write_to_bas = []

        # this data structure is used for bacnet_release_go()
        log_of_points_written = []

        # either 1's or 0's
        clg_cmds_running = []

        #loop through count compressors running
        for cmd in clg_compressor_data[0].values():

            _log.info(f'[RTU Load Shed INFO] - clg_compressor_data cmd: {cmd}')
            clg_cmds_running.append(cmd)


        #total_clg_cmds_running = sum(clg_cmds_running)
        total_clg_cmds_running = 3
        _log.info(f'[RTU Load Shed INFO] - TOTAL CLG CMDs RUNNING IS: {total_clg_cmds_running}')
        _log.info(f'[RTU Load Shed INFO] - bacnet_override_go write_to_bas: {write_to_bas}')


        if total_clg_cmds_running <= 2:
            _log.info(f'[RTU Load Shed INFO] - 2 STAGES OF CLG: NOT ENOUGH CLG IS RUNNING ONLY 2 STAGES')

            if log_of_points_written:
                _log.info(f'[RTU Load Shed INFO] - 2 STAGES OF CLG: No Need to Release stage 3 and 4 overrides as no overrides are applied!')                           

        elif total_clg_cmds_running == 3:
            _log.info(f'[RTU Load Shed INFO] - 3 STAGES OF CLG: RUNNING NEED TO TURN OFF 3 AND 4')

            if self.last_go_around_clg_running == total_clg_cmds_running:
                _log.info(f'[RTU Load Shed INFO] - 3 STAGES OF CLG: SAME AMOUNT OF CLG IS RUNNING AS LAST RUN')
                _log.info(f'[RTU Load Shed INFO] - 3 STAGES OF CLG: NO NEED TO MAKE BACNET OVERRIDES')
                return

            # Loop through data
            for obj in clg_compressor_data[0].keys():

                obj_split = obj.split("/")

                campus_topic = obj_split[0]
                building_topic = obj_split[1]
                dev_address = obj_split[2]
                dev_point = obj_split[3]

                _log.info(f'[RTU Load Shed INFO] - 3 STAGES OF CLG: clg_compressor_data obj_split: {obj_split}')

                volttron_string = f"{campus_topic}/{building_topic}/{dev_address}/{dev_point}"
                write_to_bas.append((volttron_string, 0))

                # used for releasing purposes on bacnet_release_go
                log_of_points_written.append(volttron_string)

            # NEED TO FACTOR IN REMOVING STAGE 1 and 2
            # BUT KEEP 3 and 4 TO OVERRIDE OFF
            del write_to_bas[:2]

            _log.info(f'[RTU Load Shed INFO] - 3 STAGES OF CLG: modified write_to_bas {write_to_bas}')

            self.vip.rpc.call('platform.actuator',
                            'set_multiple_points', 
                            self.core.identity, 
                            write_to_bas).get(timeout=300)

            _log.info(f'[RTU Load Shed INFO] - 3 STAGES OF CLG: bacnet_override_go BACnet OVERRIDES IMPLEMENTED!!')

            self.last_go_around_clg_running = total_clg_cmds_running

        else:

            _log.info(f'[RTU Load Shed INFO] - 4 STAGES OF CLG: RUNNING NEED TO RELEASE STAGE 3 AND OVERRIDE STAGE 4 OFF')           


            if self.last_go_around_clg_running == total_clg_cmds_running:
                _log.info(f'[RTU Load Shed INFO] - 4 STAGES OF CLG: SAME AMOUNT OF CLG IS RUNNING AS LAST RUN')
                _log.info(f'[RTU Load Shed INFO] - 4 STAGES OF CLG: NO NEED TO MAKE BACNET OVERRIDES')
                return

            counter = 0
            # Loop through data
            for obj in clg_compressor_data[0].keys():

                obj_split = obj.split("/")

                campus_topic = obj_split[0]
                building_topic = obj_split[1]
                dev_address = obj_split[2]
                dev_point = obj_split[3]

                _log.info(f'[RTU Load Shed INFO] - 4 STAGES OF CLG: clg_compressor_data obj_split: {obj_split}')

                volttron_string = f"{campus_topic}/{building_topic}/{dev_address}/{dev_point}"

                # Release stage 3
                if counter == 3:
                    _log.info(f'[RTU Load Shed INFO] - 4 STAGES OF CLG: counter 3 hit')
                    write_to_bas.append((volttron_string, None))

                    # used for releasing purposes on bacnet_release_go
                    log_of_points_written.append(volttron_string)

                # Override stage 4 off
                elif counter == 4:
                    _log.info(f'[RTU Load Shed INFO] - 4 STAGES OF CLG: counter 4 hit')
                    write_to_bas.append((volttron_string, 0))

                    # used for releasing purposes on bacnet_release_go
                    log_of_points_written.append(volttron_string)                    

                else:
                    _log.info(f'[RTU Load Shed INFO] - 4 STAGES OF CLG: counter pass hit')
                    pass

                counter += 1

            # NEED TO FACTOR IN REMOVING STAGE 1 and 2
            # BUT KEEP 3 and 4 TO OVERRIDE OFF
            #del write_to_bas[:2]

            _log.info(f'[RTU Load Shed INFO] - 4 STAGES OF CLG modified write_to_bas {write_to_bas}')

            self.vip.rpc.call('platform.actuator',
                            'set_multiple_points', 
                            self.core.identity, 
                            write_to_bas).get(timeout=300)
                            
            _log.info(f'[RTU Load Shed INFO] - bacnet_override_go BACnet OVERRIDES IMPLEMENTED!!')


        self.last_go_around_clg_running = total_clg_cmds_running
        self.bas_points_that_are_written = log_of_points_written
        self.last_adr_event_date = _now
        self.last_bacnet_override_go_time = get_aware_utc_now()


    def bacnet_release_go(self):

        if self.bacnet_releases_complete:
            return

        _log.info(f"[RTU Load Shed INFO] - bacnet_release_go called!")

        # create start and end timestamps for actuator agent scheduling
        _now = get_aware_utc_now()
        str_start = format_timestamp(_now)
        _end = _now + td(seconds=10)
        str_end = format_timestamp(_end)

        actuator_schedule_request = []
        for device in self.nested_group_map.values():
            bacnet_address = device["device_address"]
            device = '/'.join([self.building_topic, str(bacnet_address)])
            actuator_schedule_request.append([device, str_start, str_end])

        _log.info(f'[RTU Load Shed INFO] - bacnet_release_go actuator_schedule_request is {actuator_schedule_request}')


        # use actuator agent to get all zone temperature setpoint data
        actuator_sched_req_result = self.vip.rpc.call('platform.actuator', 
                                                    'request_new_schedule', 
                                                    self.core.identity, 
                                                    'my_schedule', 
                                                    'HIGH', 
                                                    actuator_schedule_request).get(timeout=90)

        _log.info(f'[RTU Load Shed INFO] - bacnet_release_go actuator_sched_req_result is {actuator_sched_req_result}')



        write_releases_to_bas = []
        for device_and_point in self.bas_points_that_are_written:

            # tuple data structure for actuator agent
            write_releases_to_bas.append((device_and_point, None))

        _log.info(f'[RTU Load Shed INFO] - write_releases_to_bas is {write_releases_to_bas}')

        self.vip.rpc.call('platform.actuator', 
                            'set_multiple_points', 
                            self.core.identity, 
                            write_releases_to_bas).get(timeout=300)


        # this is compiled in bacnet_override_go()
        self.bas_points_that_are_written.clear()

        _log.info(f'[RTU Load Shed INFO] - write_releases_to_bas finished!!!')
        _log.info(f'[RTU Load Shed INFO] - write_releases_to_bas is {write_releases_to_bas}')

        self.last_adr_event_status_string = "Success"

        self.bacnet_releases_complete = True

    # called by periodic on an interval
    def event_checkr(self):

        now_utc = get_aware_utc_now()

        self.until_start_time_seconds = (self.adr_start - now_utc).total_seconds()
        self.until_start_time_minutes = self.until_start_time_seconds / 60
        self.until_start_time_hours = self.until_start_time_minutes / 60

        self.until_end_time_seconds = (self.adr_event_ends - now_utc).total_seconds()
        self.until_end_time_minutes = self.until_end_time_seconds / 60
        self.until_end_time_hours = self.until_end_time_minutes / 60

        if self.until_start_time_seconds > 0:
            _log.info(f'[RTU Load Shed INFO] - Load Shed to start on UTC time zone: {self.adr_start}')
            _log.info(f'[RTU Load Shed INFO] - Count Down Timer To Start In Hours: {round(self.until_start_time_hours)}') 
            _log.info(f'[RTU Load Shed INFO] - Count Down Timer To Start In Minutes: {round(self.until_start_time_minutes)}')
            _log.info(f'[RTU Load Shed INFO] - Count Down Timer To Start In Seconds: {round(self.until_start_time_seconds)}') 


        '''
        if the periodic interval is short the
        possibility could happen that the previous
        event_checkr call didnt finish if alot of BACnet
        actions are being applied to the HVAC system
        '''
        if self.event_checkr_isrunning:
            return


        # to prevent the "periodic" running again when/if
        # a BACnet release/write is being appliend
        self.event_checkr_isrunning = True

        # check if the demand response event is active or not
        if now_utc >= self.adr_start and now_utc < self.adr_event_ends: #future time is greater

            _log.info(f'[RTU Load Shed INFO] - The Demand Response Event is ACTIVE!!!')
            self.bacnet_override_go()

            _log.info(f'[RTU Load Shed INFO] - Demand Response Event Is Active Successfully!!')
            _log.info(f'[RTU Load Shed INFO] - Count Down Timer To End In Hours: {round(self.until_end_time_hours)}') 
            _log.info(f'[RTU Load Shed INFO] - Count Down Timer To End In Minutes: {round(self.until_end_time_minutes)}')
            _log.info(f'[RTU Load Shed INFO] - Count Down Timer To End In Seconds: {round(self.until_end_time_seconds)}') 


        else: # event is False
            self.bacnet_release_go()

            '''
            # after dr event expires we should hit this if statement to release BAS
            if not self.bacnet_releases_complete:
                _log.info(f'[RTU Load Shed INFO] - bacnet_release_go GO!!!!')

                try:
                    self.bacnet_release_go()
                    self.bacnet_releases_complete = True
                    _log.info(f'[RTU Load Shed INFO] - bacnet_release_go SUCCESS')
                    _log.info(f'[RTU Load Shed INFO] - self.bacnet_releases_complete is {self.bacnet_releases_complete}')
                
                
                except Exception as bacnet_override_exception:
                    self.bacnet_override_error_str = bacnet_override_exception
                    self.bacnet_override_error = True
                    self.last_adr_event_status_string = "Failure"
                    _log.info(f'[RTU Load Shed INFO] - bacnet_release_go ERROR: {self.bacnet_override_error}')
            '''

        self.event_checkr_isrunning = False



    # called when agent is installed and (future)
    # when a new event comes in on the message bus
    def process_adr_event(self,event):

        now_utc = get_aware_utc_now()

        signal = event['event_signals'][0]
        intervals = signal['intervals']

        # loop through open ADR payload
        for interval in intervals:
            self.adr_start = interval['dtstart']
            self.adr_payload_value = interval['signal_payload']
            self.adr_duration = interval['duration']

            self.adr_event_ends = self.adr_start + self.adr_duration

            self.until_start_time_seconds = (self.adr_start - now_utc).total_seconds()
            self.until_start_time_minutes = self.until_start_time_seconds / 60
            self.until_start_time_hours = self.until_start_time_minutes / 60

            self.until_end_time_seconds = (self.adr_event_ends - now_utc).total_seconds()
            self.until_end_time_minutes = self.until_end_time_seconds / 60
            self.until_end_time_hours = self.until_end_time_minutes / 60




    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):

        # use dummy event until real event comes in via open ADR VEN agent
        self.process_adr_event(DUMMY_EVENT)
        _log.info(f"[RTU Load Shed INFO] - process_adr_event hit")
        _log.info(f"[RTU Load Shed INFO] - open ADR process of signal sucess!")
        _log.info(f"[RTU Load Shed INFO] - adr_start is {self.adr_start}")
        _log.info(f"[RTU Load Shed INFO] - adr_payload_value {self.adr_payload_value}")
        _log.info(f"[RTU Load Shed INFO] - adr_duration {self.adr_duration}")


        self.core.periodic(5, self.event_checkr)







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
    utils.vip_main(rtuloadshed, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
