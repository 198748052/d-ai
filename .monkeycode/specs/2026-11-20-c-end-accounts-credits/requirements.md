# Requirements Document

## Introduction

把当前单用户工具改造为面向 C 端用户的产品：邮箱注册登录、按实际字数计费的额度体系、按用户隔离的任务记录、管理员运营入口。首期不接支付，用户通过兑换码或管理员手动加字数获得额度。

## Glossary

- **用户**：通过邮箱和密码注册的账号。
- **额度**：账号可用的剩余字数，按提交文本的实际字数扣减。
- **管理员**：拥有运营权限的账号，可调整用户额度、生成兑换码、维护规则与 LLM 配置。
- **兑换码**：一次性或限次使用的充值凭证，兑换后增加额度。
- **改写任务**：一次提交文本并生成改写结果的作业。

## Requirements

### Requirement 1 注册与登录

**User Story:** AS 访客, I want 用邮箱和密码注册登录, so that 我的任务和额度能保存下来。

#### Acceptance Criteria

1. WHEN 访客提交未被占用的邮箱和不少于 8 位的密码, THE 系统 SHALL 创建用户并赠送 100 字额度。
2. WHEN 访客提交已注册的邮箱, THE 系统 SHALL 返回明确提示且不创建重复账号。
3. WHEN 用户提交正确的邮箱和密码, THE 系统 SHALL 创建会话并在浏览器写入 HttpOnly 会话 Cookie。
4. IF 邮箱格式非法或密码少于 8 位, THE 系统 SHALL 拒绝请求并说明原因。
5. WHEN 用户退出登录, THE 系统 SHALL 删除服务端会话并清除 Cookie。
6. WHILE 用户已登录, THE 系统 SHALL 在任意页面返回当前用户邮箱、角色与剩余额度。

### Requirement 2 按字数计费

**User Story:** AS 用户, I want 只为实际提交的字数付费, so that 费用与用量匹配。

#### Acceptance Criteria

1. WHEN 已登录用户创建改写任务, THE 系统 SHALL 按提交正文的实际字数（不含空白字符）扣减额度。
2. IF 剩余额度小于本次字数, THE 系统 SHALL 拒绝创建任务并返回所需字数与当前余额。
3. WHEN 任务在产出任何段落前失败, THE 系统 SHALL 把本次扣减的字数退回账户。
4. WHEN 额度发生变动, THE 系统 SHALL 写入一条流水，包含变动值、原因、变动后余额与时间。

### Requirement 3 兑换码与管理员加额度

**User Story:** AS 用户, I want 用兑换码充值, so that 不接支付也能获得额度。

#### Acceptance Criteria

1. WHEN 用户提交有效且未用尽的兑换码, THE 系统 SHALL 增加对应字数并记录流水。
2. IF 兑换码不存在、已过期或已用尽, THE 系统 SHALL 拒绝兑换并说明原因。
3. WHEN 管理员为用户增加或扣减额度, THE 系统 SHALL 更新余额并记录管理员操作的流水。
4. WHEN 管理员创建兑换码, THE 系统 SHALL 保存面额、可用次数与有效期。

### Requirement 4 数据隔离

**User Story:** AS 用户, I want 只看到自己的任务, so that 内容不被他人看到。

#### Acceptance Criteria

1. WHEN 用户查询任务列表或任务详情, THE 系统 SHALL 只返回该用户自己的任务。
2. IF 用户请求他人的任务详情, THE 系统 SHALL 返回未找到。
3. WHEN 未登录访客调用改写或任务接口, THE 系统 SHALL 返回未授权。

### Requirement 5 管理员权限

**User Story:** AS 管理员, I want 管理运营配置, so that 普通用户不会看到或改动平台配置。

#### Acceptance Criteria

1. WHEN 系统创建第一个注册用户, THE 系统 SHALL 把该用户设为管理员。
2. WHILE 用户不是管理员, THE 系统 SHALL 拒绝其读写 LLM 配置、写入规则库与删除踩坑记录。
3. WHEN 管理员访问后台, THE 系统 SHALL 提供用户列表、额度调整与兑换码生成能力。
4. WHEN 管理员查看用户列表, THE 系统 SHALL 展示邮箱、剩余额度、角色与注册时间。

### Requirement 6 C 端界面

**User Story:** AS 用户, I want 清楚看到登录状态、剩余额度和用量, so that 知道还能用多少。

#### Acceptance Criteria

1. WHILE 未登录, THE 前端 SHALL 在导航展示登录入口，并在提交改写时引导到登录页。
2. WHILE 已登录, THE 前端 SHALL 在导航展示邮箱、剩余额度与退出入口。
3. WHEN 用户打开账户页, THE 前端 SHALL 展示余额、额度流水与兑换码输入框。
4. WHILE 用户不是管理员, THE 前端 SHALL 隐藏 LLM 设置、规则库、预设与后台入口。
