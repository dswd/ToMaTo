# -*- coding: utf-8 -*-
# ToMaTo (Topology management software) 
# Copyright (C) 2010 Dennis Schwerdel, University of Kaiserslautern
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>

from django.db import models
from django.core import exceptions
import sys, time, traceback
from datetime import datetime, timedelta

from tomato import fault
from tomato.lib import db, attributes, util #@UnresolvedImport
from tomato.lib.decorators import *

# storage needs:
# <100 bytes per record
# <100 records per object
# -> <10 kb per object

TYPES = ["single", "5minutes", "hour", "day", "month", "year"]
KEEP_RECORDS = {
    "single": 15,
    "5minutes": 12,
    "hour": 24,
    "day": 30,
    "month": 12,
    "year": 5,
}

def _avg(data, weightSum):
    return sum([k * v for (k, v) in data]) / weightSum
        
def _sum(data, weightSum):
    return sum(v for (v, _) in  data)

def _timediff(begin, end):
    td = (end-begin)
    #python 2.6 has no total_seconds()
    return (td.microseconds + (td.seconds + td.days * 24 * 3600) * 10**6) / 10**6
    
def _lastRange(type_):
    if type_ == "5minutes":
        end = datetime.now().replace(second=0, microsecond=0)
        end = end.replace(minute=(end.minute / 5)*5)
        begin = end - timedelta(minutes=5)
    elif type_ == "hour":
        end = datetime.now().replace(second=0, microsecond=0, minute=0)
        begin = end - timedelta(hours=1)
    elif type_ == "day":
        end = datetime.now().replace(second=0, microsecond=0, minute=0, hour=0)
        begin = end - timedelta(days=1)
    elif type_ == "month":
        end = datetime.now().replace(second=0, microsecond=0, minute=0, hour=0, day=1)
        begin = datetime(end.year if end.month > 1 else end.year, end.month -1 if end.month > 1 else 12, 1)
    elif type_ == "year":
        end = datetime.now().replace(second=0, microsecond=0, minute=0, hour=0, day=1, month=1)
        begin = datetime(end.year - 1, 1, 1)
    return (begin, end)        
    
def _combine(begin, end, records):
    #calculate coverage
    measurements = sum([r.measurements for r in records])
    #combine attributes
    combined = Usage()
    if not measurements:
        return (combined, 0)
    combined.cputime = _sum([(r.cputime, r.measurements) for r in records], measurements)
    combined.diskspace = _avg([(r.diskspace, r.measurements) for r in records], measurements)
    combined.memory = _avg([(r.memory, r.measurements) for r in records], measurements)
    combined.traffic = _sum([(r.traffic, r.measurements) for r in records], measurements)
    return (combined, measurements)

class Usage:
    def __init__(self):
        self.cputime = 0.0
        self.memory = 0.0
        self.diskspace = 0.0
        self.traffic = 0.0
    def updateContinuous(self, name, value, data):
        lastName = "last_%s" % name
        if lastName in data:
            diff_ = value - data[lastName]
            if diff_ < 0:
                diff_ = value
            setattr(self, name, diff_)
        data[lastName] = value
    
class UsageStatistics(attributes.Mixin, models.Model):
    begin = models.DateTimeField(auto_now_add=True)
    #records: [UsageRecord]
    attrs = db.JSONField()
    
    class Meta:
        pass

    def init(self, attrs={}):
        self.attrs = {}
        self.save()
        
    def remove(self):
        self.delete()    
    
    def info(self):
        return dict([(t, [r.info() for r in self.getRecords(t)]) for t in TYPES])
       
    def getRecords(self, type_):
        return self.records.filter(type=type_)
       
    def createRecord(self, type_, begin, end, measurements, usage):
        record = UsageRecord()
        record.init(self, type_, begin, end, measurements, usage)
        record.save()
        self.records.add(record)
       
    @db.commit_after
    def update(self):
        usage = Usage()
        begin = datetime.now()
        try:
            self.element.upcast().updateUsage(usage, self.attrs)
        except exceptions.ObjectDoesNotExist:
            pass
        try:
            self.connection.upcast().updateUsage(usage, self.attrs)
        except exceptions.ObjectDoesNotExist:
            pass
        end = datetime.now()
        self.createRecord("single", begin, end, 1, usage)
        self._combine()
        self._removeOld()
        self.save()
       
    def _combine(self):
        lastType = TYPES[0]
        for type_ in TYPES[1:]:
            begin, end = _lastRange(type_)
            if self.begin > begin:
                begin = self.begin
            if self.begin > end:
                break
            if self.records.filter(type=type_, begin=begin, end=end).exists():
                break
            records = self.records.filter(type=lastType, begin__gte=begin, end__lte=end)
            usage, coverage = _combine(begin, end, records)
            self.createRecord(type_, begin, end, coverage, usage)
            lastType = type_
            
    def _removeOld(self):
        for type_ in TYPES:
            for r in self.getRecords(type_).order_by("-begin")[KEEP_RECORDS[type_]:]:
                r.delete()
    
class UsageRecord(models.Model):
    statistics = models.ForeignKey(UsageStatistics, related_name="records")
    type = models.CharField(max_length=10, choices=[(t, t) for t in TYPES]) #@ReservedAssignment
    begin = models.DateTimeField()
    end = models.DateTimeField()
    measurements = models.IntegerField()
    #using fields to save space
    memory = models.FloatField() #unit: bytes
    diskspace = models.FloatField() #unit: bytes
    traffic = models.FloatField() #unit: bytes
    cputime = models.FloatField() #unit: cpu seconds
    
    class Meta:
        pass

    def init(self, statistics, type, begin, end, measurements, usage): #@ReservedAssignment
        self.statistics = statistics
        self.type = type
        self.begin = begin
        self.end = end
        self.measurements = measurements
        self.cputime = usage.cputime
        self.memory = usage.memory
        self.diskspace = usage.diskspace
        self.traffic = usage.traffic
        self.save()

    def info(self):
        return {
            "type": self.type,
            "begin": self.begin,
            "end": self.end,
            "measurements": self.measurements,
            "usage": {"cputime": self.cputime, "diskspace": self.diskspace, "memory": self.memory, "traffic": self.traffic},
        }
        
def update():
    for us in UsageStatistics.objects.all():
        try:
            us.update()
        except:
            traceback.print_exc()
        
task = util.RepeatedTimer(60, update)