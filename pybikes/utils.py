# -*- coding: utf-8 -*-
# Copyright (C) 2010-2012, eskerda <eskerda@gmail.com>
# Distributed under the AGPL license, see LICENSE.txt

import os
import re
try:
    # Python 2
    from itertools import imap as map
except ImportError:
    # Python 3
    pass

import requests
from requests.adapters import HTTPAdapter, Retry
from shapely.geometry import Polygon, Point, box

from pybikes.base import BikeShareStation


def str2bool(v):
    return v.lower() in ["yes", "true", "t", "1"]


def sp_capwords(word):
    blacklist = [
        u'el', u'la', u'los', u'las',
        u'un', u'una', u'unos', u'unas',
        u'lo', u'al', u'del',
        u'a', u'ante', u'bajo', u'cabe', u'con', u'contra', u'de', u'desde',
        u'en', u'entre', u'hacia', u'hasta', u'mediante', u'para', u'por',
        u'según', u'sin',
        # Catala | Valencia | Mallorqui
        u'ses', u'sa', u'ses'
    ]
    word = word.lower()
    cap_lambda = lambda iw: iw[1].capitalize() if iw[0] == 0 or iw[1] not in blacklist else iw[1]
    return " ".join(map(cap_lambda, enumerate(word.split())))


class PyBikesScraper(object):
    proxy_enabled = False
    last_request = None
    ssl_verification = True
    requests_timeout = 300
    retry = False
    retry_opts = {}

    def __init__(self, cachedict=None, headers=None):
        self.headers = headers if isinstance(headers, dict) else {}
        self.headers.setdefault('User-Agent', 'PyBikes')
        self.proxies = {}
        self.session = requests.session()
        self.cachedict = cachedict

    def setUserAgent(self, user_agent):
        self.headers['User-Agent'] = user_agent

    def request(self, url, method='GET', params=None, data=None, raw=False,
                headers=None, default_encoding='UTF-8', skip_cache=False):

        if self.retry:
            retries = Retry(** self.retry_opts)
            self.session.mount(url, HTTPAdapter(max_retries=retries))

        _headers = self.headers.copy()
        _headers.update(headers or {})

        # XXX proper encode arguments for proper call args -> response
        if self.cachedict and url in self.cachedict and not skip_cache:
            response = self.cachedict[url]
        else:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                data=data,
                proxies=self.getProxies(),
                headers=_headers,
                # some endpoints might fail verification, so it's up to the spider
                # to disable it
                verify=self.ssl_verification,
                timeout=self.requests_timeout,
            )

        data = response.text

        # Somehow requests defaults to ISO-8859-1 (when no encoding
        # specified). Put it back to UTF-8 by default
        if 'charset' not in response.headers:
            if 'Content-Type' in response.headers:
                if 'text' in response.headers['Content-Type']:
                    response.encoding = default_encoding
                    data = response.text
        if raw:
            data = response.content

        if 'set-cookie' in response.headers:
            self.headers['Cookie'] = response.headers['set-cookie']
        self.last_request = response

        if self.cachedict is not None:
            self.cachedict[url] = response

        return data

    def clearCookie(self):
        if 'Cookie' in self.headers:
            del self.headers['Cookie']

    def setProxies(self, proxies):
        self.proxies = proxies

    def getProxies(self):
        if self.proxy_enabled:
            return self.proxies
        else:
            return {}

    def enableProxy(self):
        self.proxy_enabled = True

    def disableProxy(self):
        self.proxy_enabled = False


def filter_bounds(things, key, *point_bounds):
    def default_getter(thing):
        if isinstance(thing, BikeShareStation):
            return (thing.latitude, thing.longitude)
        return (thing[0], thing[1])
    key = key or default_getter

    bounds = []
    for pb in point_bounds:
        # Assume that a 2 length bound is a square NE/SW
        if len(pb) == 2:
            bb = box(min(pb[0][0], pb[1][0]),
                     min(pb[0][1], pb[1][1]),
                     max(pb[0][0], pb[1][0]),
                     max(pb[0][1], pb[1][1]))
        else:
            bb = Polygon(pb)
        bounds.append(bb)

    for thing in things:
        point = Point(*key(thing))
        if not any(map(lambda pol: pol.contains(point), bounds)):
            continue
        yield thing


class Keys:
    def __getattr__(self, key):
        return os.environ.get('PYBIKES_%s' % key.upper())

keys = Keys()
keys.bicimad = {
    'passkey': keys.bicimad_passkey,
    'clientid': keys.bicimad_clientid,
}
keys.weelo = {
    'client_id': keys.weelo_client_id,
    'client_secret': keys.weelo_client_secret,
}
keys.deutschebahn = {
    'client_id': keys.deutschebahn_client_id,
    'client_secret': keys.deutschebahn_client_secret,
}
