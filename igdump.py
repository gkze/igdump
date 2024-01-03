#!/usr/bin/env python
from __future__ import annotations

import json
import logging
import os
from argparse import ArgumentParser, Namespace
from collections.abc import Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from enum import StrEnum
from http import HTTPStatus
from http.client import HTTPResponse
from multiprocessing import cpu_count
from pathlib import Path
from sys import argv
from typing import Any, Literal, cast
from urllib.error import HTTPError
from urllib.parse import urlencode, urljoin, urlunparse
from urllib.request import Request, urlopen
import sqlite3
from sqlite3 import Connection, Cursor


PROG: str = Path(__file__).name
URL_SCHEME: str = "https"
LOG_FMT = "%(asctime)s %(levelname)s %(message)s"
LOGGER = logging.getLogger(Path(__file__).stem)

Headers = Mapping[str, Any]


@dataclass(frozen=True)
class Instagram:
    app_id: int = 936619743392459
    host: str = "www.instagram.com"
    base_path: str = "api/v1/"
    following_page_max: int = 200


class InstagramAPIPath(StrEnum):
    WEB_PROFILE = "users/web_profile_info/"
    FOLLOWING = "friendships/{user_id}/following/"


InstagramAPIPathLiteral = Literal[
    InstagramAPIPath.WEB_PROFILE, InstagramAPIPath.FOLLOWING
]


@dataclass(frozen=True)
class Cookie:
    sessionid: str
    ds_user_id: int | None = None

    def __str__(self) -> str:
        return "; ".join("=".join(map(str, e)) for e in self.__dict__.items()) + ";"


class Header(StrEnum):
    Cookie = "Cookie"
    InstagramAppId = "X-Ig-App-Id"


class InstagramClient:
    def __init__(
        self: InstagramClient, session_id: str, user_id: int, threads: int | None = None
    ) -> None:
        self.session_id = session_id
        self.user_id = user_id
        self.threads = threads

    def make_request(
        self: InstagramClient,
        path: InstagramAPIPathLiteral,
        path_params: dict[str, Any] = {},
        query_params: Mapping[str, Any] = {},
    ) -> HTTPResponse | None:
        # fmt: off
        url = urlunparse((
            URL_SCHEME,
            Instagram.host,
            urljoin(Instagram.base_path, path.value.format(**path_params)),
            "",
            urlencode(query_params),
            "",
        ))
        LOGGER.debug(f"Sending request with url: {url}")

        try:
            resp: HTTPResponse = urlopen(Request(url, headers={
                Header.Cookie.value: str(Cookie(self.session_id, self.user_id)),
                Header.InstagramAppId.value: str(Instagram.app_id),
            }))
            # fmt: on

            if resp.status >= HTTPStatus.BAD_REQUEST:
                LOGGER.error(
                    f"Got unsuccessful response for {url}: {resp.status} - {resp.read()}"
                )
                return

            return resp

        except HTTPError as e:
            LOGGER.exception(e)
            raise

    def get_profile(self: InstagramClient, user_name: str) -> Mapping[str, Any]:
        LOGGER.info(f"Getting profile for user {user_name}")
        return json.load(
            cast(
                HTTPResponse,
                self.make_request(
                    InstagramAPIPath.WEB_PROFILE, query_params={"username": user_name}
                ),
            )
        )["data"]["user"]

    def get_following_slice(
        self: InstagramClient,
        user_id: int | None = None,
        max_id: int = Instagram.following_page_max,
        count: int = Instagram.following_page_max,
    ) -> HTTPResponse:
        LOGGER.info(
            f"Getting following slice for user ID {user_id} @ max_id of {max_id}"
        )
        return cast(
            HTTPResponse,
            self.make_request(
                InstagramAPIPath.FOLLOWING,
                {"user_id": user_id or self.user_id},
                {"count": count, "max_id": max_id},
            ),
        )

    def get_following_all(
        self: InstagramClient, user_name: str = ""
    ) -> list[Mapping[str, Any]]:
        user_profile: Mapping[str, Any] = self.get_profile(user_name)
        slices = range(
            Instagram.following_page_max,
            user_profile["edge_follow"]["count"] + Instagram.following_page_max,
            Instagram.following_page_max,
        )

        futures: list[Future] = []
        with ThreadPoolExecutor(self.threads or len(slices)) as tpe:
            for max_id in slices:
                futures.append(
                    tpe.submit(
                        self.get_following_slice, int(user_profile["id"]), max_id
                    )
                )

        return sum((json.load(f.result())["users"] for f in futures), [])


def parse_args(argv: list[str]) -> Namespace:
    parser: ArgumentParser = ArgumentParser(PROG, f"{PROG} [...]")
    parser.add_argument(
        "-s",
        "--session-id",
        type=str,
        help="Session ID",
        default=os.getenv("IG_SESSION_ID"),
    )
    parser.add_argument(
        "-i", "--user-id", type=int, help="User ID", default=os.getenv("IG_USER_ID")
    )
    parser.add_argument(
        "-n",
        "--user-name",
        type=str,
        help="User name",
        default=os.getenv("IG_USER_NAME"),
    )
    parser.add_argument(
        "-t",
        "--threads",
        type=int,
        help="Thread pool size",
        default=os.getenv("IGDUMP_NUM_THREADS", cpu_count()),
    )
    parser.add_argument(
        "-l", "--log-level", type=str, help="Log level", default=logging.INFO
    )

    return parser.parse_args(argv)


def main(argv: list[str] = []) -> None:
    args: Namespace = parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format=LOG_FMT)

    client: InstagramClient = InstagramClient(args.session_id, args.user_id)
    con: Connection = sqlite3.connect("following.sqlite3")
    cur: Cursor = con.cursor()

    cur.execute(
        """
        CREATE TABLE following (
            name text,
            username text,
            bio text,
            followers integer,
            following integer,
            category text
        )"""
    )

    following_all: list[Mapping[str, Any]] = client.get_following_all("gkze")

    futures: list[Future] = []
    with ThreadPoolExecutor(args.threads) as tpe:
        for profile in following_all:
            futures.append(tpe.submit(client.get_profile, profile["username"]))

    for account in [f.result() for f in futures]:
        data = (
            account["full_name"],
            account["username"],
            account["biography"],
            account["edge_followed_by"]["count"],
            account["edge_follow"]["count"],
            account["category_enum"],
        )

        LOGGER.info(f"Inserting {data}")
        cur.executemany("INSERT INTO following VALUES(?, ?, ?, ?, ?, ?)", data)

    con.commit()


if __name__ == "__main__":
    main(argv[1:])
