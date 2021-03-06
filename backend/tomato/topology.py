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

from .db import *
from .generic import *
import time
from lib import logging #@UnresolvedImport
from accounting import UsageStatistics
from .auth.permissions import PermissionMixin, Role
from . import scheduler
from .lib.error import UserError #@UnresolvedImport

class TimeoutStep:
	INITIAL = 0
	WARNED = 9
	STOPPED = 10
	DESTROYED = 20


class Topology(Entity, PermissionMixin, BaseDocument):
	"""
	:type permissions: list of Permission
	:type totalUsage: UsageStatistics
	:type site: Site
	:type clientData: dict
	"""
	from .auth.permissions import Permission
	from .host import Site
	permissions = ListField(EmbeddedDocumentField(Permission))
	totalUsage = ReferenceField(UsageStatistics, db_field='total_usage', required=True, reverse_delete_rule=DENY)
	timeout = FloatField(required=True)
	timeoutStep = IntField(db_field='timeout_step', required=True, default=TimeoutStep.INITIAL)
	site = ReferenceField(Site, reverse_delete_rule=NULLIFY)
	name = StringField()
	clientData = DictField(db_field='client_data')
	meta = {
		'ordering': ['name'],
		'indexes': [
			'name', ('timeout', 'timeoutStep')
		]
	}
	type = 'Topology'

	@property
	def elements(self):
		return Element.objects(topology=self)

	@property
	def connections(self):
		return Connection.objects(topology=self)

	DOC = ""

	def init(self, owner, attrs=None):
		if not attrs: attrs = {}
		self.setRole(owner, Role.owner)
		self.totalUsage = UsageStatistics.objects.create()
		self.timeout = time.time() + config.TOPOLOGY_TIMEOUT_INITIAL
		self.timeoutStep = TimeoutStep.WARNED #not sending a warning for initial timeout
		self.save()
		self.name = "Topology [%s]" % self.idStr
		self.modify(attrs)

	def isBusy(self):
		return hasattr(self, "_busy") and self._busy
	
	def setBusy(self, busy):
		self._busy = busy

	def checkUnknownAttribute(self, key, value):
		self.checkRole(Role.manager)
		UserError.check(key.startswith("_"), code=UserError.UNSUPPORTED_ATTRIBUTE, message="Unsupported attribute")
		return True

	def setUnknownAttributes(self, attrs):
		for key, value in attrs.items():
			if key.startswith("_"):
				self.clientData[key[1:]] = value

	def checkModify(self, attr):
		self.checkRole(Role.manager)
		UserError.check(not self.isBusy(), code=UserError.ENTITY_BUSY, message="Object is busy")

	def checkAction(self, action):
		self.checkRole(Role.manager)
		if action in ["start", "prepare"]:
			UserError.check(self.timeout > time.time(), code=UserError.TIMED_OUT, message="Topology has timed out")
		UserError.check(not self.isBusy(), code=UserError.ENTITY_BUSY, message="Object is busy")
		return True

	def action_prepare(self):
		self._compoundAction(action="prepare", stateFilter=lambda state: state=="created", 
							 typeOrder=["kvmqm", "openvz", "repy", "tinc_vpn", "udp_endpoint"],
							 typesExclude=["kvmqm_interface", "openvz_interface", "repy_interface", "external_network", "external_network_endpoint"])
	
	def action_destroy(self):
		self.action_stop()
		self._compoundAction(action="destroy", stateFilter=lambda state: state=="prepared",
							 typeOrder=["tinc_vpn", "udp_endpoint", "kvmqm", "openvz", "repy"],
							 typesExclude=["kvmqm_interface", "openvz_interface", "repy_interface", "external_network", "external_network_endpoint"])
	
	def action_start(self):
		self.action_prepare()
		self._compoundAction(action="start", stateFilter=lambda state: state!="started",
							 typeOrder=["tinc_vpn", "udp_endpoint", "external_network", "kvmqm", "openvz", "repy"],
							 typesExclude=["kvmqm_interface", "openvz_interface", "repy_interface"])
		
	
	def action_stop(self):
		self._compoundAction(action="stop", stateFilter=lambda state: state=="started", 
							 typeOrder=["kvmqm", "openvz", "repy", "tinc_vpn", "udp_endpoint", "external_network"],
							 typesExclude=["kvmqm_interface", "openvz_interface", "repy_interface"])

	def action_renew(self, timeout):
		timeout = float(timeout)
		UserError.check(timeout <= config.TOPOLOGY_TIMEOUT_MAX or currentUser().hasFlag(Flags.GlobalAdmin),
			code=UserError.INVALID_VALUE, message="Timeout is greater than the maximum")
		self.timeout = time.time() + timeout
		self.timeoutStep = TimeoutStep.INITIAL if timeout > config.TOPOLOGY_TIMEOUT_WARNING else TimeoutStep.WARNED
		
	def _compoundAction(self, action, stateFilter, typeOrder, typesExclude):
		# execute action in order
		for type_ in typeOrder:
			for el in self.elements:
				if el.type != type_ or not stateFilter(el.state) or el.type in typesExclude:
					continue
				el.action(action)
		# execute action on rest
		for el in self.elements:
			if not stateFilter(el.state) or el.type in typesExclude or el.type in typeOrder:
				continue
			el.action(action)

	def checkRemove(self, recurse=True):
		self.checkRole(Role.owner)
		UserError.check(not self.isBusy(), code=UserError.ENTITY_BUSY, message="Object is busy")
		UserError.check(recurse or self.elements.count()==0, code=UserError.NOT_EMPTY,
			message="Cannot remove topology with elements")
		UserError.check(recurse or self.connections.count()==0, code=UserError.NOT_EMPTY,
			message="Cannot remove topology with connections")
		for el in self.elements:
			el.checkRemove(recurse=recurse)
		for con in self.connections:
			con.checkRemove()

	def remove(self, recurse=True):
		self.checkRemove(recurse)
		logging.logMessage("info", category="topology", id=self.idStr, info=self.info())
		logging.logMessage("remove", category="topology", id=self.idStr)
		if self.id:
			self.delete()
		self.totalUsage.remove()

	def modify_site(self, val):
		self.site = Site.get(val)

	def modifyRole(self, user, role):
		UserError.check(role in Role.RANKING or not role, code=UserError.INVALID_VALUE, message="Invalid role",
			data={"roles": Role.RANKING})
		self.checkRole(Role.owner)
		UserError.check(user != currentUser(), code=UserError.INVALID_VALUE, message="Must not set permissions for yourself")
		logging.logMessage("permission", category="topology", id=self.idStr, user=user.name, role=role)
		self.setRole(user, role)
			
	def sendMail(self, role=Role.manager, **kwargs):
		for permission in self.permissions:
			if Role.RANKING.index(permission.role) >= Role.RANKING.index(role):
				permission.user.sendMail(**kwargs)

	@property
	def maxState(self):
		states = self.elements.distinct('state')
		for state in ['started', 'prepared', 'created']:
			if state in states:
				return state
		return 'created'

	def info(self, full=False):
		if not currentUser() is True and not currentUser().hasFlag(Flags.Debug):
			self.checkRole(Role.user)
		info = Entity.info(self)
		if full:
			# Speed optimization: use existing information to avoid database accesses
			els = self.elements
			childs = {}
			for el in els:
				if not el.parentId:
					continue
				if not el.parentId in childs:
					childs[el.parentId] = []
				chs = childs[el.parentId]
				chs.append(el.id)
			connections = {}
			for el in els:
				if not el.connectionId:
					continue
				if not el.connectionId in connections:
					connections[el.connectionId] = []
				cons = connections[el.connectionId]
				cons.append(el)
			elements = [el.info(childs.get(el.id,[])) for el in els]
			connections = [con.info(connections.get(con.id, [])) for con in self.connections]
		else:
			elements = [str(el.id) for el in self.elements.only('id')]
			connections = [str(con.id) for con in self.connections.only('id')]
		info.update(elements=elements, connections=connections)
		for key, val in self.clientData.items():
			info["_"+key] = val
		return info

	def updateUsage(self):
		self.totalUsage.updateFrom([el.totalUsage for el in self.elements]
								 + [con.totalUsage for con in self.connections])

	def __str__(self):
		return "%s [#%s]" % (self.name, self.id)

	ACTIONS = {
		"start": Action(action_start, check=lambda self: self.checkAction('start'), paramSchema=schema.Constant({})),
		"stop": Action(action_stop, check=lambda self: self.checkAction('stop'), paramSchema=schema.Constant({})),
		"prepare": Action(action_prepare, check=lambda self: self.checkAction('prepare'), paramSchema=schema.Constant({})),
		"destroy": Action(action_destroy, check=lambda self: self.checkAction('destroy'), paramSchema=schema.Constant({})),
		"renew": Action(action_renew, check=lambda self, timeout: self.checkAction('renew'),
			paramSchema=schema.StringMap(items={'timeout': schema.Number(minValue=0.0)}, required=['timeout'])),
	}
	ATTRIBUTES = {
		"id": IdAttribute(),
		"permissions": Attribute(readOnly=True, get=lambda self: {str(p.user): p.role for p in self.permissions},
			schema=schema.StringMap(additional=True)),
		"usage": Attribute(readOnly=True, get=lambda self: self.totalUsage.latest, schema=schema.StringMap(additional=True, null=True)),
		"site": Attribute(get=lambda self: self.site.name if self.site else None,
			set=modify_site, schema=schema.Identifier(null=True)),
		"elements": Attribute(readOnly=True, schema=schema.List()),
		"connections": Attribute(readOnly=True, schema=schema.List()),
		"timeout": Attribute(field=timeout, readOnly=True, schema=schema.Number()),
		"state_max": Attribute(field=maxState, readOnly=True, schema=schema.String()),
		"name": Attribute(field=name, schema=schema.String())
	}


def get(id_, **kwargs):
	try:
		return Topology.objects.get(id=id_, **kwargs)
	except Topology.DoesNotExist:
		return None

def getAll(**kwargs):
	return list(Topology.objects.filter(**kwargs))

def create(attrs=None):
	if not attrs: attrs = {}
	UserError.check(not currentUser().hasFlag(Flags.NoTopologyCreate), code=UserError.DENIED,
		message="User can not create new topologies")
	top = Topology()
	top.init(owner=currentUser(), attrs=attrs)
	logging.logMessage("create", category="topology", id=top.idStr)
	logging.logMessage("info", category="topology", id=top.idStr, info=top.info())
	return top
	
	
def timeout_task():
	now = time.time()
	setCurrentUser(True) #we are a global admin
	for top in Topology.objects.filter(timeoutStep=TimeoutStep.INITIAL, timeout__lte=now+config.TOPOLOGY_TIMEOUT_WARNING):
		logging.logMessage("timeout warning", category="topology", id=top.idStr)
		top.sendMail(subject="Topology timeout warning: %s" % top, message="The topology %s will time out soon. This means that the topology will be first stopped and afterwards destroyed which will result in data loss. If you still want to use this topology, please log in and renew the topology." % top)
		top.timeoutStep = TimeoutStep.WARNED
		top.save()
	for top in Topology.objects.filter(timeoutStep=TimeoutStep.WARNED, timeout__lte=now):
		logging.logMessage("timeout stop", category="topology", id=top.idStr)
		top.action_stop()
		top.timeoutStep = TimeoutStep.STOPPED
		top.save()
	for top in Topology.objects.filter(timeoutStep=TimeoutStep.STOPPED, timeout__lte=now-config.TOPOLOGY_TIMEOUT_WARNING):
		logging.logMessage("timeout destroy", category="topology", id=top.idStr)
		top.action_destroy()
		top.timeoutStep = TimeoutStep.DESTROYED
		top.save()

scheduler.scheduleRepeated(600, timeout_task)

from .elements import Element
from .connections import Connection
from .auth import Flags
from .auth.permissions import Permission
from . import currentUser, config, setCurrentUser
from .host.site import Site
