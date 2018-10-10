# Pushl

A simple tool that parses content feeds and sends out appropriate push notifications (WebSub, Webmention, etc.) when they change.

See http://publ.beesbuzz.biz/blog/113-Some-thoughts-on-WebMention for the motivation.

## Usage

### Setup

First, you'll want to have your Atom (or RSS) feed implement [the WebSub protocol](https://indieweb.org/WebSub). The short version is that you should have a `<link rel="hub" href="http://path/to/hub" />` in your Atom feed.

There are a number of WebSub hubs available; I use [Superfeedr](http://pubsubhubbub.superfeedr.com).

For [WebMentions](https://indieweb.org/Webmention), configure your site templates with the various microformats; by default, Pushl will use the following tags as the top-level entry container, in descending order of priority:

* Anything with a `class` of `h-entry`
* An `<article>` tag
* Anything with a `class` of `entry`

This may become configurable in the future.

### Sending notifications

```bash
pip install pushl
pushl -c cache_dir http://example.com/feed.xml
```

If your feed implements [RFC 5005](https://tools.ietf.org/html/rfc5005), the `-a` flag will scan past entries for WebMention as well.

You will probably want to run this in a cron job or the like.

### Advanced configuration

TODO: whitelist/blacklist for `rel` links for outgoing WebMentions

## TODO

Tool should be pip-installable (DONE)

Mechanisms should include:

* WebSub (DONE)
* WebMention
    * Should notify all extant URLs as well as any which were in the previous version but are now gone
    * but be sensitive to ones with a `rel` that isn't in a whitelist (e.g. don't want author, self, nofollow, nonotify, navigation, etc)
* Configurable Publ/Jekyll/Octopress/etc. syndication? (i.e. write out syndicated content to $HOME/mysite.example.com/content/syndicated/foo.md, possibly mirroring images locally)
    * Needs to have some sort of configurable template for the headers, with defaults for the more common systems (Publ, Pelican, Jekyll?)
    * Could probably use Jinja2 for this
    * (Is probably out of scope though)
    * (yeah this is definitely out of scope)

Other worthwhile ideas:

* Support [RFC 5005](https://tools.ietf.org/html/rfc5005) (DONE)
* Detect deletions, maybe? This is a SHOULD in Webmention, and a good idea for the syndication
    * This is a lot easier in RFC 5005 feeds
    * Or possibly, compare set of current items with the items listed in the previous feed retrieval, and send out one last ping/update for the items which disappeared from the feed (since Webmention doesn't differentiate between those two cases)
* Have post-run hooks (for example, syncing syndicated content stores via git-based deployment or whatever)
