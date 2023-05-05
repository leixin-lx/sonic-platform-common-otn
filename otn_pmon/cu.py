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

import psutil
from functools import lru_cache
from otn_pmon.common import *
from otn_pmon.alarm import Alarm
from otn_pmon.pm import Pm
import otn_pmon.periph as periph
import otn_pmon.db as db
from otn_pmon.thrift_api.ttypes import led_color, periph_type

class CoreCollector() :
    def __init__(self) :
        self.count = psutil.cpu_count(logical = False)

    def execute(self) :
        def gen_pm(tname, kname, pm_name, val) :
            pm15 = Pm(tname, kname, pm_name, Pm.PM_TYPE_15)
            pm24 = Pm(tname, kname, pm_name, Pm.PM_TYPE_24)
            pm15.update(val)
            pm24.update(val)

        times_percent = psutil.cpu_times_percent(percpu=True)
        if not times_percent :
            return

        for i in range(self.count) :
            cpu = times_percent[i]
            total = cpu.user + cpu.nice + cpu.system + cpu.iowait + cpu.irq +\
                    cpu.softirq + cpu.steal + cpu.guest + cpu.guest_nice
            # the type of percentage is uint8
            gen_pm("CPU", f"CPU-{i}", "Total",  int(total))
            gen_pm("CPU", f"CPU-{i}", "User",   int(cpu.user))
            gen_pm("CPU", f"CPU-{i}", "Kernel", int(cpu.system))
            gen_pm("CPU", f"CPU-{i}", "Nice",   int(cpu.nice))
            gen_pm("CPU", f"CPU-{i}", "Idle",   int(cpu.idle))
            gen_pm("CPU", f"CPU-{i}", "Wait",   int(cpu.iowait))

@lru_cache()
class Cu(periph.Periph):
    CPU_MEMORY_USAGE_THRESH = 80
    CPU_MEMORY_CLEAR_THRESH = 60

    def __init__(self, id):
        super().__init__(periph_type.CU, id)
    
    def initialize_state(self):
        inv = self.get_inventory()
        if not inv :
            return

        data = [
            ("part-no", inv.pn),
            ("serial-no", inv.sn),
            ("mfg-date", inv.mfg_date),
            ("hardware-version", inv.hw_ver),
            ("software-version", inv.sw_ver),
            ("parent", "CHASSIS-1"),
            ("empty", "false"),
            ("removable", "false"),
            ("mfg-name", "alibaba"),
            ("oper-status", periph.slot_status_to_oper_status(slot_status.INIT)),
        ]

        self.dbs[db.STATE_DB].set(self.table_name, self.name, data)

    def __get_memory(self) :
        memory = {}
        tmp = psutil.virtual_memory()
        memory["utilized"] = tmp.used
        memory["available"] = tmp.available
        memory["percent"] = tmp.percent
        return memory

    def update_pm(self) :
        temp = self.get_temperature()
        super().update_pm("Temperature", temp)

        memory = self.__get_memory()
        super().update_pm("MemoryUtilized", memory["utilized"])
        super().update_pm("MemoryAvailable", memory["available"])

        percent = int(psutil.cpu_percent())
        super().update_pm("CpuUtilization", percent)

        CoreCollector().execute()

    def update_alarm(self) :
        memory_hi = Alarm(self.name, "MEM_USAGE_HIGH")
        memory = self.__get_memory()
        if memory["percent"] > Cu.CPU_MEMORY_USAGE_THRESH :
            memory_hi.create()
        elif memory["percent"] < Cu.CPU_MEMORY_CLEAR_THRESH :
            memory_hi.clear()
