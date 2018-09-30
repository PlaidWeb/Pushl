# Pushl

A simple tool that parses content feeds and sends out appropriate push notifications (WebSub, Webmention, etc.) when they change.

See http://publ.beesbuzz.biz/blog/113-Some-thoughts-on-WebMention for the motivation.

## Back-of-the-envelope design

Tool should be pip-installable

Should be configurable with a list of feeds (from command line or from a config.yaml or whatever) and associated push mechanisms to provide

Mechanisms should include:

* WebSub (with configured endpoint)
* WebNotify (just calls into [ronkyuu](https://github.com/bear/ronkyuu) or [webmention-tools](https://github.com/vrypan/webmention-tools) or something)
* Configurable Publ/Jekyll/Octopress/etc. syndication? (i.e. write out syndicated content to $HOME/mysite.example.com/content/syndicated/foo.md, possibly mirroring images locally)
    * Needs to have some sort of configurable template for the headers, with defaults for the more common systems (Publ, Pelican, Jekyll?)

Should be smart about caching; for example:

* Store the feed locally, and use if-modified-since and file fingerprinting to determine if items need to be retrieved
* Store the retrieved items locally, and use if-modified-since and file fingerprinting to determine if items need to be updated
* This storage directory should be configurable, and have a reasonable default (like $HOME/.local/share/Pushl)

Other worthwhile ideas:

* Support [RFC 5005](https://tools.ietf.org/html/rfc5005)
* Detect deletions, maybe? This is a SHOULD in Webmention, and a good idea for the syndication
    * This is a lot easier in RFC 5005 feeds
    * Or possibly, compare set of current items with the items listed in the previous feed retrieval, and send out one last ping/update for the items which disappeared from the feed (since Webmention doesn't differentiate between those two cases)
* Have post-run hooks (for example, syncing syndicated content stores via git-based deployment or whatever)
