# Copyright (C) 2018-2019 Dmitry Marakasov <amdmi3@amdmi3.ru>
#
# This file is part of repology
#
# repology is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# repology is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with repology.  If not, see <http://www.gnu.org/licenses/>.

import json
import os

import requests

from repology.atomic_fs import AtomicDir
from repology.fetchers import PersistentData, ScratchDirFetcher
from repology.fetchers.http import PoliteHTTP
from repology.logger import Logger


class ElasticSearchFetcher(ScratchDirFetcher):
    def __init__(self, url, scroll_url=None, es_query=None, es_filter=None, es_fields=None, es_size=5000, es_scroll='1m', fetch_timeout=5, fetch_delay=None):
        self.url = url
        self.scroll_url = scroll_url
        self.scroll = es_scroll

        self.request_data = {}
        if es_fields:
            self.request_data['fields'] = es_fields
        if es_query:
            self.request_data['query'] = es_query
        if es_filter:
            self.request_data['filter'] = es_filter
        if es_size:
            self.request_data['size'] = es_size

        self.do_http = PoliteHTTP(timeout=fetch_timeout, delay=fetch_delay)

    def _do_fetch_scroll(self, statedir: AtomicDir, logger: Logger) -> None:
        numpage = 0

        logger.log('getting page {}'.format(numpage))
        response = self.do_http('{}?scroll={}'.format(self.url, self.scroll), json=self.request_data).json()

        scroll_id = response['_scroll_id']

        while response['hits']['hits']:
            with open(os.path.join(statedir.get_path(), '{}.json'.format(numpage)), 'w', encoding='utf-8') as pagefile:
                json.dump(response['hits']['hits'], pagefile)

            numpage += 1

            logger.log('getting page {}'.format(numpage))
            response = self.do_http('{}?scroll={}&scroll_id={}'.format(self.scroll_url, self.scroll, scroll_id)).json()

        try:
            self.do_http(self.scroll_url, method='DELETE', json={'scroll_id': scroll_id}).json()
        except requests.exceptions.HTTPError as e:
            # we don't care too much if removing the scroll fails, it'll timeout anyway
            # XXX: but log this
            logger.log('failed to DELETE scroll, server reply follows:\n' + e.response.text, severity=Logger.ERROR)
            logger.log(e.response.text, severity=Logger.ERROR)
            pass

    def _do_fetch(self, statedir: AtomicDir, persdata: PersistentData, logger: Logger) -> bool:
        try:
            self._do_fetch_scroll(statedir, logger)
        except requests.exceptions.HTTPError as e:
            # show server reply as it contains the failure cause
            logger.log('request failed, server reply follows:\n' + e.response.text, severity=Logger.ERROR)
            logger.log(e.response.text, severity=Logger.ERROR)
            raise

        return True
