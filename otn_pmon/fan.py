##
#   Copyright (c) 2021 Alibaba Group and Accelink Technologies
#
#   Licensed under the Apache License, Version 2.0 (the "License"); you may
#   not use this file except in compliance with the License. You may obtain
#   a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
#   THIS CODE IS PROVIDED ON AN *AS IS* BASIS, WITHOUT WARRANTIES OR
#   CONDITIONS OF ANY KIND, EITHER EXPRESS OR IMPLIED, INCLUDING WITHOUT
#   LIMITATION ANY IMPLIED WARRANTIES OR CONDITIONS OF TITLE, FITNESS
#   FOR A PARTICULAR PURPOSE, MERCHANTABILITY OR NON-INFRINGEMENT.
#
#   See the Apache Version 2.0 License for specific language governing
#   permissions and limitations under the License.
##

import threading
from otn_pmon.common import *
from otn_pmon.alarm import Alarm
import otn_pmon.periph as periph
import otn_pmon.public as public
import otn_pmon.db as db
from functools import lru_cache
from otn_pmon.thrift_api.ttypes import error_code, periph_type
from otn_pmon.thrift_client import thrift_try

@lru_cache()
class Fan(periph.Periph) :
    def __init__(self, id) :
        super().__init__(periph_type.FAN, id)
        self.boot_timeout_secs = 10
        self.control_mode = fan_control_mode.AUTO

    def initialize_state(self) :
        inv = self.get_inventory()
        if not inv :
            return

        s_status = self.get_slot_status()
        if not s_status or s_status == slot_status.EMPTY :
            s_status = slot_status.INIT

        data = [
            ('part-no', inv.pn),
            ('serial-no', inv.sn),
            ('mfg-date', inv.mfg_date),
            ('hardware-version', inv.hw_ver),
            ("parent", "CHASSIS-1"),
            ("empty", "false"),
            ('removable', "true"),
            ("mfg-name", "alibaba"),
            ("oper-status", periph.slot_status_to_oper_status(s_status)),
            ("slot-status", get_slot_status_name(s_status)),
        ]

        self.dbs[db.STATE_DB].set(self.table_name, self.name, data)

    def get_speed_rate(self) :
        ok, rate = self.dbs[db.STATE_DB].get_field(self.table_name, self.name, "speed-rate")
        if not ok or not rate :
            return None

        return float(rate)

    def set_speed_rate(self, rate) :
        if not isinstance(rate, int) :
            return

        # set speed-rate to driver
        def inner(client):
            return client.set_fan_speed_rate(self.id, rate)

        ret = thrift_try(inner)
        if ret != error_code.OK :
            LOG.log_error(f"set {self.name} speed-rate {rate} to driver failed")
            return
        LOG.log_info(f"set {self.name} speed-rate {rate} success")
        # update the value of speed-rate in STATE_DB
        self.dbs[db.STATE_DB].set_field(self.table_name, self.name, "speed-rate", str(rate))

    def __get_speed(self) :
        def inner(client) :
            return client.get_fan_speed(self.id)

        result = thrift_try(inner)
        if result.ret != error_code.OK :
            return None
        return result.speed

    def __get_speed_spec(self) :
        def inner(client) :
            return client.get_fan_speed_spec(self.id)
        return thrift_try(inner)

    def update_pm(self) :
        temp = self.get_temperature()
        super().update_pm("Temperature", temp)

        speed = self.__get_speed()
        if not speed :
            return
        super().update_pm("Speed", speed.front)
        super().update_pm("Speed_2", speed.behind)

    def update_alarm(self) :
        alarm = None
        s_status = None

        speed = self.__get_speed()
        if not speed :
            return
        max_speed = speed.front if speed.front >= speed.behind else speed.behind
        min_speed = speed.front if speed.front <= speed.behind else speed.behind

        speed_spec = self.__get_speed_spec()
        if max_speed > speed_spec.max :
            alarm = Alarm(self.name, "FAN_HIGH")
        elif max_speed == 0 or min_speed == 0 :
            alarm = Alarm(self.name, "FAN_FAIL")
            s_status = slot_status.UNKNOWN
        elif min_speed < speed_spec.min  :
            alarm = Alarm(self.name, "FAN_LOW")
        
        if alarm :
            alarm.createAndClearOthers()
            if s_status :
                self.update_slot_status(s_status)
        else :
            cur_status = self.get_slot_status()
            if cur_status == slot_status.READY :
                Alarm.clearBy(self.name, "FAN_")

class FanControl(threading.Thread) :
    SPEED_RATE_L1 = 30
    SPEED_RATE_L2 = 35
    SPEED_RATE_L3 = 40
    SPEED_RATE_L4 = 45
    SPEED_RATE_L5 = 75
    SPEED_RATE_L6 = 100
    # level, rate, upshift_temp_thresh, downshift_temp_thresh
    CTRL_RULES = [
        ["S1", SPEED_RATE_L1, 35, 0],
        ["S2", SPEED_RATE_L2, 38, 33],
        ["S3", SPEED_RATE_L3, 41, 36],
        ["S4", SPEED_RATE_L4, 44, 39],
        ["S5", SPEED_RATE_L5, 48, 42],
        ["S6", SPEED_RATE_L6, 0,  46],
    ]
    def __init__(self, interval = 1) :
        threading.Thread.__init__(self)
        self.interval = interval
        self.stop = threading.Event()
        self.list = self.__get_fan_list()

    def __get_fan_list(self) :
        list = []
        start = public.get_first_slot_id(periph_type.FAN)
        end = public.get_last_slot_id(periph_type.FAN)
        for i in range (start, end + 1) :
            f = Fan(i)
            if f.presence() :
                list.append(f)
        return list

    def run_manual(self, rate) :
        for f in self.list :
            f.set_speed_rate(rate)

    def _get_ctrl_rule_index(self, rate) :
        if not rate or rate <= FanControl.SPEED_RATE_L1 :
            return 0
        elif FanControl.SPEED_RATE_L1 < rate <= FanControl.SPEED_RATE_L2 :
            return 1
        elif FanControl.SPEED_RATE_L2 < rate <= FanControl.SPEED_RATE_L3 :
            return 2
        elif FanControl.SPEED_RATE_L3 < rate <= FanControl.SPEED_RATE_L4 :
            return 3
        elif FanControl.SPEED_RATE_L4 < rate <= FanControl.SPEED_RATE_L5 :
            return 4
        elif FanControl.SPEED_RATE_L5 < rate <= FanControl.SPEED_RATE_L6 :
            return 5

    def _expect_speed_rate(self, fan) :
        rate = None
        cur_temp = public.get_inlet_temp()
        index = self._get_ctrl_rule_index(fan.get_speed_rate())
        ctrl_info = FanControl.CTRL_RULES[index]
        upshift_temp_thresh = ctrl_info[2]
        downshift_temp_thresh = ctrl_info[3]
        # upshift
        if upshift_temp_thresh != 0 and cur_temp > upshift_temp_thresh :
            rate = FanControl.CTRL_RULES[index + 1][1]
        # downshift
        if downshift_temp_thresh != 0 and cur_temp < downshift_temp_thresh :
            rate = FanControl.CTRL_RULES[index - 1][1]

        return rate

    def _need_full_speed(self) :
        # get inlet temperature failed
        temp = public.get_inlet_temp()
        if not temp :
            return True

        # any fan is absent
        fan_num = periph.get_periph_number(periph_type.FAN)
        fan_presence_num = len(self.list)
        if fan_num != fan_presence_num :
            return True

        # alarms exists
        linecard_num = periph.get_periph_number(periph_type.LINECARD)
        start = public.get_first_slot_id(periph_type.LINECARD)
        for i in range (start, linecard_num + 1) :
            dbc = db.Client(i, db.STATE_DB).db
            # HIGH_TEMPERATURE_ALARM
            if len(dbc.keys("*HIGH_TEMPERATURE_ALARM*")) != 0 :
                return True
            # SLOT_COMM_FAIL
            if len(dbc.keys("*SLOT_COMM_FAIL*")) != 0 :
                return True

        return False

    def run_auto(self) :
        if self._need_full_speed() :
            self.run_manual(FanControl.SPEED_RATE_L6)
            return

        for f in self.list :
            if f.control_mode != fan_control_mode.AUTO :
                continue
            expect_rate = self._expect_speed_rate(f)
            print(f"set {f.name} speed {expect_rate}")
            if not expect_rate :
                continue
            f.set_speed_rate(expect_rate)

    def run(self) :
        while not self.stop.wait(self.interval) :
            self.run_auto()
