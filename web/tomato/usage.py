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

import json

from django.shortcuts import render
from lib import wrap_rpc, AuthError

@wrap_rpc
def host(api, request, name): #@ReservedAssignment
    if not api.user:
        raise AuthError()
    usage=api.host_usage(name)
    return render(request, "main/usage.html", {'usage': json.dumps(usage), 'name': 'Host %s' % name})


@wrap_rpc
def organization(api, request, name): #@ReservedAssignment
    if not api.user:
        raise AuthError()
    usage=api.organization_usage(name)
    return render(request, "main/usage.html", {'usage': json.dumps(usage), 'name': 'Organization %s' % name})
