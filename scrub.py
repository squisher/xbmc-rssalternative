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
import sys

def clear(path):
  print (_di_+"Scrubbing " + path)
  try:
    shutil.rmtree(path)
  except Exception, e:
    print (_di_+"Error deleting "+path+": " + str(e))

if len(sys.argv) <= 1:
  print(_di_+"Need an argument what to clean")
  sys.exit(1)

if sys.argv[1] == 'clear_state':
  clear(_dataDir_)
elif sys.argv[1] == 'clear_cache':
  clear(_tempDir_)

print (_di_+"Done cleaning!")
