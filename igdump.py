#!/usr/bin/env python
from __future__ import annotations

import json
import os
from argparse import ArgumentParser, Namespace
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from http.client import HTTPResponse
from pathlib import Path
from sys import argv
from typing import Any, Literal
from urllib.parse import urlencode, urljoin, urlunparse
from urllib.request import Request, urlopen

PROG: str = Path(__file__).name
URL_SCHEME: str = "https"

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
    def __init__(self: InstagramClient, session_id: str, user_id: int) -> None:
        self.session_id = session_id
        self.user_id = user_id

    def make_request(
        self: InstagramClient,
        path: InstagramAPIPathLiteral,
        path_params: dict[str, Any] = {},
        query_params: Mapping[str, Any] = {},
    ) -> HTTPResponse:
        return urlopen(
            Request(
                urlunparse(
                    (
                        URL_SCHEME,
                        Instagram.host,
                        urljoin(Instagram.base_path, path.value.format(**path_params)),
                        "",
                        urlencode(query_params),
                        "",
                    )
                ),
                headers={
                    Header.Cookie.value: str(Cookie(self.session_id, self.user_id)),
                    Header.InstagramAppId.value: str(Instagram.app_id),
                },
            )
        )

    def get_profile(self: InstagramClient, user_name: str) -> Mapping[str, Any]:
        return json.load(
            self.make_request(
                InstagramAPIPath.WEB_PROFILE, query_params={"username": user_name}
            )
        )["data"]["user"]

    def get_following_slice(
        self: InstagramClient,
        user_id: int | None = None,
        max_id: int = Instagram.following_page_max,
        count: int = Instagram.following_page_max,
    ) -> HTTPResponse:
        return self.make_request(
            InstagramAPIPath.FOLLOWING,
            {"user_id": user_id or self.user_id},
            {"count": count, "max_id": max_id},
        )

    def get_following_all(
        self: InstagramClient, user_name: str = ""
    ) -> list[Mapping[str, Any]]:
        following_all: list[Mapping[str, Any]] = []
        user_profile: Mapping[str, Any] = self.get_profile(user_name)

        for max_id in range(
            Instagram.following_page_max,
            user_profile["edge_follow"]["count"] + Instagram.following_page_max,
            Instagram.following_page_max,
        ):
            following_all.append(
                json.load(
                    self.get_following_slice(int(user_profile["id"]), max_id=max_id)
                )["users"]
            )

        return following_all


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

    return parser.parse_args(argv)


def main(argv: list[str] = []) -> None:
    args: Namespace = parse_args(argv)
    print(
        json.dumps(
            InstagramClient(args.session_id, args.user_id).get_following_all("gkze")
        )
    )


if __name__ == "__main__":
    main(argv[1:])
