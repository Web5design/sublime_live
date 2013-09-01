Sublime Text 3 : sublime_live
==========================

This is a Sublime Text 3 module to give plugin developers the ability to make areas of pages clickable or live.

It works by hanging what we refer to as a sublime_live.LiveView of a sublime.View, this is used to extend sublime.View's functionality.
We also introduce the concept of live regions, which are sublime_live.LiveRegion.
These are wrappers of sublime.Region that when added to a LiveView allow a developer to hang functionality off areas of a view.
Because sublime_live.LiveRegion's are wrappers of sublime.Region's a developer can also give a LiveRegion different background, foreground and caret colors to the rest of the page, as they can already do with sublime.Regions when adding then to a sublime.View.

For some simple examples of what is possible see:
    [sublime_live_console](https://github.com/sligodave/sublime_live_console)
    [sublime_live_color_schemes](https://github.com/sligodave/sublime_live_color_schemes)
    [sublime_live_tictactoe](https://github.com/sligodave/sublime_live_tictactoe)

I see this really as providing a developer with the ability to write plugins that maybe provide interactive access to API's or other functionality that users desire.

## Install:

On it's own, this module does nothing.
You need to place it in your plugin or somewhere where your plugin can import and use it.

**Note**

    One important note:
        You must import the LiveEventListener for clicks to be heard and acted upon.
            from .sublime_live import UpdateLiveViewCommand, LiveEventListener

## Issues / Suggestions:

Send on any suggestions or issues.

## Copyright and license
Copyright 2013 David Higgins

[MIT License](LICENSE)
