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

import xbmc,xbmcaddon
import os.path

__all__ = ['_addon_id_', '_settings_', '_addonDir_', '_dataDir_', '_tempDir_', '_lastCached_',
           '_di_']

_addon_id_      = "plugin.audio.rssalternative"
_settings_      = xbmcaddon.Addon(id=_addon_id_)
_addonDir_      = _settings_.getAddonInfo('path')
_dataDir_       = xbmc.translatePath("special://profile/addon_data/%s/" % _addon_id_)
_tempDir_       = xbmc.translatePath("special://temp/%s/" % _addon_id_)
_lastCached_    = os.path.join(_dataDir_,'last_cached')
_di_            = "RSS-ALT "
