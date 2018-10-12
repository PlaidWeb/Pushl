# Pushl

A simple tool that parses content feeds and sends out appropriate push notifications (WebSub, webmention, etc.) when they change.

See http://publ.beesbuzz.biz/blog/113-Some-thoughts-on-WebMention for the motivation.

## Features

* Will send WebSub notifications for feeds which declare a WebSub hub
* Will send webnotify notifications for entries discovered on those feeds or specified directly
* Can perform autodiscovery of additional feeds on entry pages
* Can do a full site submission on Atom feeds configured with [RFC 5005](https://tools.ietf.org/html/rfc5005)
* When configured to use a cache directory, can detect entry deletions and updates to implement the webmention update and delete protocols

## Usage

### Setup

First, you'll want to have your Atom (or RSS) feed implement [the WebSub protocol](https://indieweb.org/WebSub). The short version is that you should have a `<link rel="hub" href="http://path/to/hub" />` in your feed's top-level element.

There are a number of WebSub hubs available; I use [Superfeedr](http://pubsubhubbub.superfeedr.com).

For [WebMentions](https://indieweb.org/Webmention), configure your site templates with the various microformats; by default, Pushl will use the following tags as the top-level entry container, in descending order of priority:

* Anything with a `class` of `h-entry`
* An `<article>` tag
* Anything with a `class` of `entry`

For more information on how to configure your templates, see the [microformats h-entry specification](http://microformats.org/wiki/h-entry).23

### Sending notifications

```bash
pip install pushl
pushl -c cache_dir http://example.com/feed.xml
```

If your feed implements [RFC 5005](https://tools.ietf.org/html/rfc5005), the `-a` flag will scan past entries for WebMention as well.

While you can run it without the `-c` argument, its use is highly recommended so that subsequent runs are both less spammy and so that it can detect changed and deleted entries, for the best webmention support.

### Advanced usage

#### Pings from individual entries

If you just want to send webmentions from an entry page without processing an entire feed, the `-e/--entry` flag indicates that the following URLs are pages or entries, rather than feeds; e.g.

    pushl -e http://example.com/some/page

will simply send the webmentions for that page.

#### Additional feed discovery

The `-r/--recurse` flag will discover any additional feeds that are declared on entries. This is useful if you have per-category feeds that you would also like to send WebSub notifications on.

Note that `-r` and `-e` in conjunction will also cause the feed declared on the entry page to be processed further. While it is tempting to use this in a feed autodiscovery context e.g.

    pushl -re http://example.com/blog/

this will also send webmentions from the blog page itself which is probably *not* what you want to do.

## My setup

I use [`pipenv`](http://pipenv.org) to keep my Python environments separate. My initial setup looked something like this:

```bash
mkdir $(HOME)/pushl
cd $(HOME)/pushl
pipenv install pushl
```

and created this script as `$(HOME)/pushl/run.sh`:

```bash
#!/bin/sh

cd $(dirname "$0")
LOG=$(date +%Y%m%d.log)
date >> $LOG
flock -n run.lock $HOME/.local/bin/pipenv run pushl -rvvc cache http://beesbuzz.biz/feed http://publ.beesbuzz.biz/feed >> "$LOG" 2>&1
```

Then I have a cron job:

```crontab
*/15 * * * * $HOME/pushl/run.sh
```

which runs it every 15 minutes.
