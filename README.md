# Pushl

A simple tool that parses content feeds and sends out appropriate push notifications (WebSub, webmention, etc.) when they change.

See the blog post "[Some Thoughts on Webmention](http://publ.beesbuzz.biz/blog/113-Some-thoughts-on-WebMention)" for the motivation.

## Features

* Supports any feed supported by [feedparser](https://github.com/kurtmckee/feedparser)
    and [mf2py](https://github.com/microformats/mf2py) (RSS, Atom, HTML pages containing
    `h-entry`, etc.)
* Will send WebSub notifications for feeds which declare a WebSub hub
* Will send WebMention notifications for entries discovered on those feeds or specified directly
* Can request that the [Wayback Machine](https://web.archive.org/) do an archival of any pages you link to for posterity
* Can perform autodiscovery of additional feeds on entry pages
* Can do a full backfill on Atom feeds configured with [RFC 5005](https://tools.ietf.org/html/rfc5005)
* When configured to use a cache directory, can detect entry deletions and updates to implement the webmention update and delete protocols (as well as saving some time and bandwidth)

## Site setup

If you want to support WebSub, have your feed implement [the WebSub protocol](https://indieweb.org/WebSub). The short version is that you should have a `<link rel="hub" href="http://path/to/hub" />` in your feed's top-level element.

There are a number of WebSub hubs available; I use [Superfeedr](http://pubsubhubbub.superfeedr.com).

For [WebMentions](https://indieweb.org/Webmention), configure your site templates with the various microformats; by default, Pushl will use the following tags as the top-level entry container, in descending order of priority:

* Anything with a `class` of `h-entry`
* An `<article>` tag
* Anything with a `class` of `entry`

For more information on how to configure your site templates, see the [microformats h-entry specification](http://microformats.org/wiki/h-entry).

### mf2 feed notes

If you're using an mf2 feed (i.e. an HTML-formatted page with `h-entry` declarations), only entries with a `u-url` property will be used for sending webmentions; further, Pushl will retrieve the page from that URL to ensure it has the full content. (This is to work around certain setups where the `h-feed` only shows summary text.)

Also, there is technically no requirement for an HTML page to declare an `h-feed`; all entities marked up with `h-entry` will be consumed.

## Installation

The easiest way to install pushl is via [pipx](https://pipx.pypa.io/stable/installation/), with e.g.

```bash
pipx install pushl
```

You can also install pushl as a dependency in whatever other Python virtual environment you're using (via [poetry](https://python-poetry.org/) or the like), and this will make the pushl wrapper script available in its path.

## Usage

### Basic

```bash
pushl -c $HOME/var/pushl-cache http://example.com/feed.xml
```

While you can run it without the `-c` argument, its use is highly recommended so that subsequent runs are both less spammy and so that it can detect changes and deletions.

### Sending pings from individual entries

If you just want to send webmentions from an entry page without processing an entire feed, the `-e/--entry` flag indicates that the following URLs are pages or entries, rather than feeds; e.g.

```bash
pushl -e http://example.com/some/page
```

will simply send the webmentions for that page.

### Additional feed discovery

The `-r/--recurse` flag will discover any additional feeds that are declared on entries and process them as well. This is useful if you have per-category feeds that you would also like to send WebSub notifications on. For example, [my site](http://beesbuzz.biz) has per-category feeds which are discoverable from individual entries, so `pushl -r http://beesbuzz.biz/feed` will send WebSub notifications for all of the categories which have recent changes.

Note that `-r` and `-e` in conjunction will also cause the feed declared on the entry page to be processed further. While it is tempting to use this in a feed autodiscovery context e.g.

```bash
pushl -re http://example.com/blog/
```

this will also send webmentions from the blog page itself which is probably *not* what you want to have happen.

### Backfilling old content

If your feed implements [RFC 5005](https://tools.ietf.org/html/rfc5005), the `-a` flag will scan past entries for WebMention as well. It is recommended to only use this flag when doing an initial backfill, as it can end up taking a long time on larger sites (and possibly make endpoint operators very grumpy at you). To send updates of much older entries it's better to just use `-e` to do it on a case-by-case basis.

### Dual-protocol/multi-domain websites

If you have a website which has multiple URLs that can access it (for example, http+https, or multiple domain names), you generally only want WebMentions to be sent from the canonical URL. The best solution is to use `<link rel="canonical">` to declare which one is the real one, and Pushl will use that in sending the mentions; so, for example:


```bash
pushl -r https://example.com/feed http://example.com/feed http://alt-domain.example.com/feed
```

As long as both `http://example.com` and `http://alt-domain.example.com` declare the `https://example.com` version as canonical, only the webmentions from `https://example.com` will be sent.

If, for some reason, you can't use `rel="canonical"` you can use the `-s/--websub-only` flag on Pushl to have it only send WebSub notifications for that feed; for example:

```bash
pushl -r https://example.com/feed -s https://other.example.com/feed
```

will send both Webmention and WebSub for `https://example.com` but only WebSub for `https://other.example.com`.

### Wayback Machine archival

If you set the `-k`/`--wayback-machine` parameter, then anything you link to will be queued up for archival on [the Wayback Machine](https://web.archive.org/), meaning that if the remote resource disappears, you have a better chance of being able to update your link to an archived snapshot later.

## Automated updates

`pushl` can be run from a cron job, although it's a good idea to use `flock -n` to prevent multiple instances from stomping on each other. An example cron job for updating a site might look like:

```crontab
*/5 * * * * flock -n $HOME/.pushl-lock pushl -rc $HOME/.pushl-cache http://example.com/feed
```

### My setup

In my setup, I have `pushl` installed in my website's environment (which is managed by `poetry`):

```bash
cd $HOME/beesbuzz.biz
poetry install pushl
```

and created this script as `$HOME/beesbuzz.biz/pushl.sh`:

```bash
#!/bin/bash

cd $(dirname "$0")
LOG=logs/pushl-$(date +%Y%m%d.log)

# redirect log output
if [ "$1" == "quiet" ] ; then
    exec >> $LOG 2>&1
else
    exec 2>&1 | tee -a $LOG
fi

# add timestamp
date

# run pushl
flock -n $HOME/var/pushl/run.lock $HOME/.local/bin/poetry run pushl -rvvkc $HOME/var/pushl \
    https://beesbuzz.biz/feed\?push=1 \
    http://publ.beesbuzz.biz/feed\?push=1 \
    https://tumblr.beesbuzz.biz/rss \
    https://novembeat.com/feed\?push=1 \
    http://beesbuzz.biz/feed\?push=1 \
    -s http://beesbuzz.biz/feed-summary https://beesbuzz.biz/feed-summary

# while we're at it, clean out the log and pushl cache directory
find logs $HOME/var/pushl -type f -mtime +30 -print -delete
```

Then I have a cron job:

```crontab
*/15 * * * * $HOME/beesbuzz.biz/pushl.sh quiet
```

which runs it every 15 minutes.

I also have a [git deployment hook](http://publ.beesbuzz.biz/441) for my website, and its final step (after restarting `gunicorn`) is to run `pushl.sh`, in case a maximum latency of 15 minutes just isn't fast enough.
