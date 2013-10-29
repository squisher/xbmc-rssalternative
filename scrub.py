#
#  Copyright 2013 David Mohr "squisher"
#
#  This Program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2, or (at your option)
#  any later version.
#
#  This Program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; see the file COPYING.  If not, write to
#  the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.
#  http://www.gnu.org/copyleft/gpl.html
#

from common import *
import shutil

try:
  print (_di_+"Scrubbing " + _dataDir_)
  shutil.rmtree(_dataDir_)
  print (_di_+"Scrubbing " + _tempDir_)
  shutil.rmtree(_tempDir_)
  print (_di_+"All clean!")
except Exception, e:
  print (_di_+"Error deleting temporary data: " + str(e))
