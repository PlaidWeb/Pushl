# Pushl

A simple tool that parses content feeds and sends out appropriate push notifications (WebSub, Webmention, etc.) when they change.

See http://publ.beesbuzz.biz/blog/113-Some-thoughts-on-WebMention for the motivation.

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

### Advanced configuration

TODO: whitelist/blacklist for `rel` links for outgoing WebMentions

### My setup

I use `pipenv` to keep my Python environments separate.

On my server I created the directory `$(HOME)/pushl` and in it I ran the command:

```bash
pipenv install pushl
```

and created this script as `$(HOME)/pushl/run.sh`:

```bash
#!/bin/sh

cd $(dirname "$0")
LOG=$(date +%Y%m%d.log)
flock -n .lockfile pipenv run pushl -rvc cache http://beesbuzz.biz/feed http://publ.beesbuzz.biz/feed >> "$LOG" 2>&1
```

Then I have a cron job:

```crontab
*/15 * * * * $(HOME)/pushl/run.sh
```

which runs it every 15 minutes.