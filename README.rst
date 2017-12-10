
Notex: Package
=============================

This project aimed to create a document specification format which has the same aims as LaTeX, but different implementation. Some design goals:

* Based on familiar tools (html, css).
* More geared towards modern media (web, interactive).
* Faster and simpler compilation than LaTeX.
* Less historical baggage; fewer quirks and hacks.
* Designed for extensibility, proper package manager included.
* Separation of content and style, but with easily editable style.
* Support simultaneous editing through easy merging.
* Explicit versioning over eternal compatibility.

Like LaTeX, it's not WYSIWYG, and it works well with SVC.

**It is currently on hold or perhaps discontinued**. I don't write many reports anymore, so I'm not very motivated anymore.

Components
-----------------------------

* Core_ - the core notex engine that compiles documents (just infrastructure; most functionality should be in packages).
* `Package index`_ - Package index where notex extensions are collected (own copies can be ran).
* `Package manager`_ - Client-side package manager for notex.
* `Package template`_ - Notex package base infrastructure (necessary for core and index).
* Pages_ - Notex addon to split document into paged format (the default is scrollable webpages).
* `Various packages`_ Some packages which will be split off when ready.

.. _Core: https://github.com/mverleg/notex_core
.. _`Package template`: https://github.com/mverleg/notex_package
.. _`Package index`: https://github.com/mverleg/notex_PI
.. _`Package manager`: https://github.com/mverleg/notex_PM
.. _Pages: https://github.com/mverleg/notex_pages
.. _`Various packages`: https://github.com/mverleg/notex_pkgs



