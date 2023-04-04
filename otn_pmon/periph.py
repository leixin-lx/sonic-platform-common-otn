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

import json
from threading import Timer
from otn_pmon.thrift_api.ttypes import periph_type
from otn_pmon.thrift_client import thrift_try
from otn_pmon.common import *
import otn_pmon.db as db
from otn_pmon.alarm import Alarm
from otn_pmon.pm import Pm, clearPmByName
from sonic_py_common.device_info import get_path_to_platform_dir

def get_dev_spec() :
    platform_path = get_path_to_platform_dir()
    # platform_path = "/usr/share/sonic/platform"
    spec_path = f"{platform_path}/dev_spec.json"
    with open(spec_path, 'r', encoding='utf8') as fp:
        return json.load(fp) 

def get_periph_number(type) :
    spec = get_dev_spec()
    type_name = periph_type._VALUES_TO_NAMES[type]
    if type_name :
        return spec["number"][type_name]
    return 0

def get_periph_expected_pn(type) :
    spec = get_dev_spec()
    type_name = periph_type._VALUES_TO_NAMES[type]
    if type_name :
        return spec["expected-pn"][type_name]
    return None

class Periph(object):
    def __init__(self, type, id):
        self.type = type
        self.id = id
        self.name = self.__get_name()
        self.table_name = periph_type._VALUES_TO_NAMES[type]
        self.dbs = db.get_dbs(self.name, [db.CONFIG_DB, db.STATE_DB, db.COUNTERS_DB])
        self.state_initialized = False

    def __get_name(self) :
        type_string = periph_type._VALUES_TO_NAMES[self.type]
        if self.type == periph_type.FAN or self.type == periph_type.PSU or self.type == periph_type.LINECARD :
            name = f"{type_string}-1-{self.id}"
        else :
            name = f"{type_string}-{self.id}"
        return name

    def synchronize(self) :
        try:
            if self.get_presence() :
                # self.initialize()
                self.synchronize_presence()
                # print("{} synchronize_presence done".format(self.name))
            else :
                self.synchronize_not_presence()
                # print("{} synchronize_not_presence done".format(self.name))
        except Exception as e :
            LOG.log_warning(f"Failed to synchronize {self.name} as error : {e}")
            # raise e

    def synchronize_presence(self) :
        if not self.state_initialized :
            # clear all alarms before initializing
            Alarm.clearBy(self.name)

            self.initialize_state()
            self.state_initialized = True
            # start a timer to check whether booting successed or failed
            if hasattr(self, 'boot_timeout_secs') :
                self.start_boot_timer(self.boot_timeout_secs)
        else :
            # print("{} update_state doing".format(self.name))
            self.update_state()
            self.update_alarm()
            self.update_pm()

    def synchronize_not_presence(self):
        self.state_initialized = False
        self.dbs[db.STATE_DB].delete_entry(self.table_name, self.name)
        clearPmByName(self.name)
 
        data = [
            ("empty", "true"),
            ("slot-status", get_slot_status_name(slot_status.EMPTY)),
        ]
        self.dbs[db.STATE_DB].set(self.table_name, self.name, data)

        card_miss = Alarm(self.name, "CRD_MISS")
        card_miss.createAndClearOthers()

    def update_state(self) :
        # check unknown and mismatch
        if self.unknown() :
            self.update_slot_status(slot_status.UNKNOWN)
            return
        if self.mismatch() :
            self.update_slot_status(slot_status.MISMATCH)
            return

        # only the slot-status of the linecard is updated by southbound api
        if self.type == periph_type.LINECARD :
            # do nothing if the linecard is still initializing.
            if self.get_slot_status() == slot_status.INIT :
                return
        else :
            self.update_slot_status(slot_status.READY)

    def update_pm(self, pm_name, value):
        pm15 = Pm(self.table_name, self.name, pm_name, Pm.PM_TYPE_15)
        pm24 = Pm(self.table_name, self.name, pm_name, Pm.PM_TYPE_24)
        pm15.update(value)
        pm24.update(value)

    def mismatch(self) :
        return False

    def unknown(self) :
        return False

    def update_alarm(self):
        pass

    def start_boot_timer(self, timeout) :
        def handler(self) :
            s_status = self.get_slot_status()
            # slot_status changed as boot finished with timeout
            if slot_status.INIT == s_status :
                self.update_slot_status(slot_status.BOOTFAIL)
                boot_fail = Alarm(self.name, 'CRD_BOOT_FAIL')
                boot_fail.createAndClearOthers()
            LOG.log_info(f"{self.name} boot finished with {get_slot_status_name(s_status)}")

        boot_timer = Timer(timeout, handler, (self, ))
        boot_timer.start()
        LOG.log_info(f"{self.name} boot timer with timeout({timeout}s) started")

    def update_slot_status(self, status) :
        if not self.removable() :
            return
        state_db = self.dbs[db.STATE_DB]
         # compare with the slot-status in db
        _, db_s_status = state_db.get_field(self.table_name, self.name, "slot-status")
        if db_s_status and status != get_slot_status_value(db_s_status.upper()) :
            state_db.set_field(self.table_name, self.name, "slot-status", get_slot_status_name(status))

        # oper-status need to update with the updation of slot-status
        _, db_o_status = state_db.get_field(self.table_name, self.name, "oper-status")
        if db_o_status and db_o_status != slot_status_to_oper_status(status) :
            state_db.set_field(self.table_name, self.name, "oper-status", slot_status_to_oper_status(status))
    
    def removable(self) :
        if self.type in (periph_type.LINECARD, periph_type.FAN, periph_type.PSU) :
            return True
        return False

    def initialize(self):
        def inner(client):
            return client.initialize(self.type, self.id)
        return thrift_try(inner)
      
    def get_presence(self):
        def inner(client):
            return client.periph_presence(self.type, self.id)
        return thrift_try(inner)

    def get_version(self):
        def inner(client):
            return client.get_periph_version(self.type, self.id)
        return thrift_try(inner)

    def get_temperature(self):
        def inner(client):
            return client.get_periph_temperature(self.type, self.id)
        
        temp = thrift_try(inner)
        if temp != INVALID_TEMPERATURE :
            temp = temp / 100
        
        return temp

    def get_slot_status(self):
        state_db = self.dbs[db.STATE_DB]
        ok, status = state_db.get_field(self.table_name, self.name, "slot-status")
        if ok and  status in slot_status._NAMES_TO_VALUES :
            return get_slot_status_value(status.upper())

        return None

    def get_periph_eeprom(self):
        def inner(client):
            return client.get_periph_eeprom(self.type, self.id)
        return thrift_try(inner)

    def set_led_color(self, type, id, color):
        def inner(client):
            return client.set_led_color(type, id, color)
        return thrift_try(inner)