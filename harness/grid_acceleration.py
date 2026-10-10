# BSD notice applies to the Nav2 Bresenham-derived portion below.
# Copyright (c) 2008, 2013, Willow Garage, Inc.
# All rights reserved.
#
# Software License Agreement (BSD License 2.0)
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above
#    copyright notice, this list of conditions and the following
#    disclaimer in the documentation and/or other materials provided
#    with the distribution.
#  * Neither the name of Willow Garage, Inc. nor the names of its
#    contributors may be used to endorse or promote products derived
#    from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# Author: Eitan Marder-Eppstein
#         David V. Lu!!

"""Opt-in scalar Amanatides-Woo/Nav2 Bresenham kernels; same cells/order.

No new map policy, approximation, skip or threshold. A ContextVar scopes use to
one mapper call; other robot instances/threads retain default-off behavior.
Source/measurements: egomap47 README. No extra environment dependencies.
"""
from contextvars import ContextVar
from contextlib import contextmanager
import math
import numpy as np

OPTION='scalar_rays_v1'
_ENABLED=ContextVar('own_grid_scalar_rays',default=False)
enabled=_ENABLED.get

@contextmanager
def using(option='off'):
    if option not in ('off',OPTION):raise ValueError('UNKNOWN_MAP_ACCELERATION')
    token=_ENABLED.set(option==OPTION)
    try:yield
    finally:_ENABLED.reset(token)


def dda(start,end,resolution):
    # Keep the legacy vector initialization/float64 rounding. Only the repeated
    # two-element ndarray reductions are replaced by scalar comparisons/adds.
    a,b=np.asarray(start,float)/resolution,np.asarray(end,float)/resolution
    ix,iy=map(int,np.floor(a));ex,ey=map(int,np.floor(b))
    dx,dy=map(float,b-a)
    sx,sy=(1 if dx>0 else -1 if dx<0 else 0),(1 if dy>0 else -1 if dy<0 else 0)
    tx=(ix+(sx>0)-float(a[0]))/dx if dx else math.inf
    ty=(iy+(sy>0)-float(a[1]))/dy if dy else math.inf
    dtx=abs(1/dx) if dx else math.inf;dty=abs(1/dy) if dy else math.inf
    cells=[(ix,iy)]
    while ix!=ex or iy!=ey:
        # Legacy np.argmin resolves an exact tie to x, with finished axes masked.
        if (tx if ix!=ex else math.inf)<=(ty if iy!=ey else math.inf):
            ix+=sx;tx+=dtx
        else:iy+=sy;ty+=dty
        cells.append((ix,iy))
    return cells


def bresenham(start,end):
    # Nav2 costmap_2d.hpp: raytraceLine -> bresenham2D. Preserve half-error,
    # dominant-axis tie and endpoint exactly, using two scalar integer coords.
    x,y=map(int,start);ex,ey=map(int,end);dx,dy=ex-x,ey-y
    sx,sy=(1 if dx>0 else -1),(1 if dy>0 else -1)
    ax,ay=abs(dx),abs(dy)
    if ax>=ay:
        error=ax//2
        for _ in range(ax):
            yield x,y
            x+=sx;error+=ay
            if error>=ax:y+=sy;error-=ax
    else:
        error=ay//2
        for _ in range(ay):
            yield x,y
            y+=sy;error+=ax
            if error>=ay:x+=sx;error-=ay
    yield x,y


def install(mapper,*,map_acceleration='off'):
    if map_acceleration=='off':return mapper
    if map_acceleration!=OPTION:raise ValueError('UNKNOWN_MAP_ACCELERATION')
    original=mapper.receive
    def receive(**kwargs):
        with using(map_acceleration):return original(**kwargs)
    mapper.receive=receive
    return mapper
