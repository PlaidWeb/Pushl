# Pushl

A simple tool that parses content feeds and sends out appropriate push notifications (WebSub, webmention, etc.) when they change.

See http://publ.beesbuzz.biz/blog/113-Some-thoughts-on-WebMention for the motivation.

## Features

* Will send WebSub notifications for feeds which declare a WebSub hub
* Will send WebMention notifications for entries discovered on those feeds or specified directly
* Can perform autodiscovery of additional feeds on entry pages
* Can do a full backfill on Atom feeds configured with [RFC 5005](https://tools.ietf.org/html/rfc5005)
* When configured to use a cache directory, can detect entry deletions and updates to implement the webmention update and delete protocols (as well as saving some time and bandwidth)


## Site setup

First, you'll want to have your Atom (or RSS) feed implement [the WebSub protocol](https://indieweb.org/WebSub). The short version is that you should have a `<link rel="hub" href="http://path/to/hub" />` in your feed's top-level element.

There are a number of WebSub hubs available; I use [Superfeedr](http://pubsubhubbub.superfeedr.com).

For [WebMentions](https://indieweb.org/Webmention), configure your site templates with the various microformats; by default, Pushl will use the following tags as the top-level entry container, in descending order of priority:

* Anything with a `class` of `h-entry`
* An `<article>` tag
* Anything with a `class` of `entry`

For more information on how to configure your site templates, see the [microformats h-entry specification](http://microformats.org/wiki/h-entry).

## Installation

You can install it using `pip` with e.g.:

```bash
pip3 install pushl
```

However, I recommend installing it in a virtual environment with e.g.:

```bash
virtualenv3 $HOME/pushl
$HOME/pushl/bin/pip3 install pushl
```

and then putting a symlink to `$HOME/pushl/bin/pushl` to a directory in your $PATH, e.g.

```bash
ln -s $HOME/pushl/bin/pushl $HOME/bin/pushl
```

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

this will also send webmentions from the blog page itself which is probably *not* what you want to do.

### Backfilling old content

If your feed implements [RFC 5005](https://tools.ietf.org/html/rfc5005), the `-a` flag will scan past entries for WebMention as well. It is recommended to only use this flag when doing an initial backfill, as it can end up taking a long time on larger sites (and possibly make endpoint operators very grumpy at you). To send updates of much older entries it's better to just use `-e` to do it on a case-by-case basis.

### Dual-protocol/multi-domain websites

If you have a website which has multiple URLs that can access it (for example, http+https, or multiple domain names), you generally only want WebMentions to be sent from the canonical URL. You can configure this in Pushl by having the secondary feeds be WebSub-only, using the `-s/--websub-only` flag:

```bash
pushl -r https://example.com/feed -s http://example.com/feed http://alt-domain.example.com/feed
```

## Automated updates

`pushl` can be run from a cron job, although it's a good idea to use `flock -n` to prevent multiple instances from stomping on each other. An example cron job for updating a site might look like:

```crontab
*/5 * * * * flock -n $HOME/.pushl-lock pushl -rc $HOME/.pushl-cache http://example.com/feed
```

### My setup

In my setup, I have `pushl` installed in my website's pipenv:

```bash
cd $HOME/beesbuzz.biz
pipenv install pushl
```

and created this script as `$HOME/beesbuzz.biz/pushl.sh`:

```bash
#!/bin/sh

cd $(dirname "$0")
LOG=$(date +%Y%m%d.log)

if [ "$1" == "quiet" ] ; then
    exec >> $LOG 2>&1
else
    exec 2>&1 | tee -a $LOG
fi

date
flock -n run.lock $HOME/.local/bin/pipenv run pushl -rvvc $HOME/var/pushl \
    https://beesbuzz.biz/feed \
    http://publ.beesbuzz.biz/feed \
    https://tumblr.beesbuzz.biz/rss \
    -s http://beesbuzz.biz/feed
```

Then I have a cron job:

```crontab
*/5 * * * * $HOME/beesbuzz.biz/pushl.sh quiet
```

which runs it every 5 minutes.

I also have a [git deployment hook](http://publ.beesbuzz.biz/441) for my website, and its final step (after restarting `gunicorn`) is to run `pushl.sh`, in case a maximum latency of 5 minutes just isn't fast enough.
