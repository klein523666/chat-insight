import assert from "node:assert/strict";
import test from "node:test";

import { apiErrorMessage } from "./api.ts";

test("结构化校验错误不会显示为 object Object", () => {
  assert.equal(
    apiErrorMessage({ detail: [{ msg: "用户名格式无效" }, { msg: "密码太短" }] }, 422),
    "用户名格式无效；密码太短",
  );
});

test("字符串错误保持原样", () => {
  assert.equal(apiErrorMessage({ detail: "Invalid setup token" }, 403), "Invalid setup token");
});
