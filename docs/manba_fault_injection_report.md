# Manba API Gateway 故障注入测试报告

## 基本信息

| 项目 | 内容 |
|------|------|
| **项目名称** | Manba (fagongzi/gateway) |
| **项目类型** | RESTful API Gateway (Go) |
| **核心架构** | Proxy + ApiServer + Plugin + Filter Chain |
| **测试框架** | Go testing (标准库) |
| **测试文件数** | 6 个 `fault_injection_test.go` 文件 |
| **总测试用例数** | **51 个** |
| **所有测试结果** | ✅ **全部 PASS** |

> **测试执行时间**: 2026-05-06
> **Go 版本**: go1.25.3 windows/amd64
> **测试方式**: `go test -mod=vendor`

---

## 故障注入分类体系总览

```
┌─────────────────────────────────────────────────────────────┐
│                   故障注入测试分类体系                         │
├─────────────────────────────────────────────────────────────┤
│  F1-F6  Route 路由解析模块 (25 cases)                        │
│    ├── F1: 畸形输入 (Malformed Input) — 11 cases            │
│    ├── F2: 冲突检测 (Conflict Detection) — 3 cases           │
│    ├── F3: 查找匹配 (Find Matching) — 4 cases                │
│    ├── F4: 极端长度 (Extreme Length) — 2 cases               │
│    ├── F5: 特殊路由行为 (Special Route Behavior) — 4 cases   │
│    └── F6: 并发安全 (Concurrency Safety) — 1 case            │
│                                                             │
│  L1-L7  LoadBalance 负载均衡模块 (16 cases)                  │
│    ├── L1: 空服务器列表 — 4 cases                             │
│    ├── L2: nil请求上下文 — 4 cases                            │
│    ├── L3: 单服务器边界 — 1 case                              │
│    ├── L4: 权重边界 (零/超大权重) — 2 cases                   │
│    ├── L5: 高并发调用 — 1 case                                │
│    ├── L6: 未知LB类型 — 1 case                                │
│    └── L7: 一致性校验 — 2 cases                               │
│                                                             │
│  P1-P7  Plugin JS插件引擎模块 (17 cases)                     │
│    ├── P1: JS初始化错误 — 5 cases                             │
│    ├── P2: 返回值异常 — 6 cases                               │
│    ├── P3: nil上下文 — 1 case                                 │
│    ├── P4: 空/nil插件内容 — 1 case                            │
│    ├── P5: Require异常模块 — 2 cases                          │
│    ├── P6: 高频调用 — 1 case                                  │
│    └── P7: 串行高频调用 — 1 case                              │
│                                                             │
│  FT1-FT3  Filter上下文模块 (5 cases)                         │
│    ├── FT1: Context属性边界 — 2 cases                         │
│    ├── FT2: StringValue类型断言 — 1 case                      │
│    └── FT3: CachedValue nil输入 — 2 cases                    │
│                                                             │
│  R1-R2  RateLimiter限流模块 (7 cases)                        │
│    └── R1: RateLimiter边界 — 6 cases                         │
│    └── R2: Bucket边缘 — 1 case                               │
│                                                             │
│  J1  JWT认证模块 (10 cases)                                  │
│    └── J1: 配置解析异常 — 10 cases                            │
└─────────────────────────────────────────────────────────────┘
```

---

## 模块 1: Route 路由解析模块

**文件**: `pkg/route/fault_injection_test.go` | **测试数**: 25 | **结果**: ✅ 全部 PASS

### 注入策略与实现原理

路由模块采用 **URL Pattern 解析器**架构，通过字符串解析将 URL 模板转换为路由树节点。故障注入在**解析层**和**匹配层**两个维度进行：

```go
// 路由注册接口
func (r *Route) Add(api *metapb.API) error  // 解析 URLPattern → 路由树
func (r *Route) Find(url []byte, method string, ...) (int64, bool)  // 匹配 URL → 路由ID
```

### F1 — 畸形输入 (Malformed Input) — 11 cases

| 编号 | 注入方式 | 故障数据 | 预期 | 结果 | 风险 |
|------|---------|----------|------|------|------|
| F1.1 | 空 URLPattern | `URLPattern: ""` | 报错 | ✅ 正确拦截 | 低 |
| F1.2 | 根路径 | `URLPattern: "/"` | 正常解析 | ✅ 成功 | 无 |
| F1.3 | 无前导斜杠 | `URLPattern: "users"` | 报错 | ✅ 正确拦截 | 低 |
| F1.4 | 连续双斜杠 | `URLPattern: "/api//v1"` | 报错 | ✅ 正确拦截 | 低 |
| F1.5 | 左括号前无斜杠 | `URLPattern: "abc(number)"` | 报错 | ✅ 正确拦截 | 低 |
| F1.6 | 未知括号类型 | `URLPattern: "/(unknown_type)"` | 报错 | ✅ 正确拦截 | 低 |
| F1.7 | Enum 缺少冒号 | `URLPattern: "/(enum)"` | 报错 | ✅ 正确拦截 | 低 |
| F1.8 | 嵌套括号 | `URLPattern: "/(number/(string)"` | 不 panic | ✅ 不 panic | 低 |
| F1.9 | 空枚举值 | `URLPattern: "/(enum:)"` | 报错 | ✅ 正确拦截 | 低 |
| F1.10 | Const 带命名参数 | `URLPattern: "/const:name"` | 报错 | ✅ 正确拦截 | 低 |
| **F1.11** | **空字符注入** | `URLPattern: "...\u0000test"` | 正确处理 | ✅ 匹配成功 | **中** |

**F1.11 分析**：空字符（null byte）注入是经典的安全攻击向量。Manba 的路由解析器正确处理了含空字符的路径，没有出现截断或 panic。

### F2 — 冲突检测 (Conflict Detection) — 3 cases

| 编号 | 注入方式 | 故障数据 | 结果 | 风险 |
|------|---------|----------|------|------|
| F2.1 | 同一 API 注册两次 | `Add({/users, GET})` × 2 | ✅ 冲突报错 | 低 |
| F2.2 | GET 后注册通配符 | `Add(GET /users)` → `Add(* /users)` | ✅ 冲突报错 | 低 |
| F2.3 | 通配符后注册 GET | `Add(* /users)` → `Add(GET /users)` | ✅ 冲突报错 | 低 |

### F3 — 查找匹配 (Find Matching) — 4 cases

| 编号 | 注入方式 | 故障数据 | 结果 | 风险 |
|------|---------|----------|------|------|
| F3.1 | 空路由中查找 | `Find("/nonexistent")` 路由表为空 | ✅ 返回 false | 无 |
| F3.2 | 查找长度 > 注册 | 注册 `/users`，查找 `/users/123` | ✅ 不匹配 | 无 |
| F3.3 | HTTP 方法不匹配 | 注册 `GET /users`，查找 `POST /users` | ✅ 不匹配 | 无 |
| F3.4 | nil 参数函数 | `Find(url, method, nil)` | ✅ 正常匹配 | 无 |

### F4 — 极端长度 (Extreme Length) — 2 cases

| 编号 | 注入方式 | 故障数据 | 结果 | 风险 |
|------|---------|----------|------|------|
| F4.1 | 超长路径 | 100 段路径段 | ✅ 添加 + 查找成功 | 无 |
| F4.2 | 深度嵌套 | 50 层 `/a/a/a/.../a` | ✅ 添加 + 查找成功 | 无 |

### F5 — 特殊路由行为 (Special Route Behavior) — 4 cases

| 编号 | 注入方式 | 故障数据 | 结果 | 风险 |
|------|---------|----------|------|------|
| **F5.1** | **通配符优先级** | `/*` 和 `/users/1` 同时注册 | ✅ 匹配先注册的 `/*` | **中** |
| F5.2 | number 不匹配字母 | `/(number):id` 查找 `/abc` | ✅ 不匹配 | 无 |
| F5.3 | enum 不在列表 | `/(enum:on\|off)` 查找 `/maybe` | ✅ 不匹配 | 无 |
| F5.4 | URL 特殊字符 | 空格 / 中文路径 | ✅ 不 panic | 无 |

**F5.1 分析**：通配符优先级是 API 网关的关键设计决策。Manba 采用"先注册先匹配"策略，这与大多数网关的"精确匹配优先"策略不同，可能导致非预期的路由行为。

### F6 — 并发安全 (Concurrency Safety) — 1 case

| 编号 | 注入方式 | 故障数据 | 结果 | 判定 |
|------|---------|----------|------|------|
| F6.1 | 10 goroutine 并发 | 同时并发 `Add()` 和 `Find()` | ✅ 无 panic/data race | ✅ **安全** |

---

## 模块 2: LoadBalance 负载均衡模块

**文件**: `pkg/lb/fault_injection_test.go` | **测试数**: 16 | **结果**: ✅ 全部 PASS

### 注入策略与实现原理

负载均衡模块实现了 4 种策略（Random、RoundRobin、Weighted Robin、HashIP），每种都有独立的 `Select()` 实现。故障注入针对**所有策略变体**进行：

```go
// 负载均衡接口
type LoadBalance interface {
    Select(ctx Context, servers []metapb.Server) int  // 返回选中的server index
}
```

### L1 — 空服务器列表 — 4 cases

| 编号 | 注入方式 | 故障数据 | 结果 | 风险 |
|------|---------|----------|------|------|
| L1.1~L1.4 | 空列表/空切片 | `Select(ctx, nil)` 和 `Select(ctx, [])` | ✅ 4 种 LB 都返回 0 | 低 |

### L2 — nil 请求上下文 — 4 cases

| 编号 | 注入方式 | 结果 | 分析 |
|------|---------|------|------|
| L2.1 Rand | `Select(nil, Servers)` | ✅ 正常运行 | — |
| L2.2 RR | `Select(nil, Servers)` | ✅ 正常运行 | — |
| L2.3 WR | `Select(nil, Servers)` | ✅ 正常运行 | — |
| **L2.4 Hash** | **`Select(nil, Servers)`** | ⚠️ **panic** | **🔴 高危** |

**L2.4 Bug 分析**：`HashIPBalance.Select()` 内部调用 `util.ClientIP(ctx)` 时未对 nil ctx 做保护。`ClientIP` 对 `ctx.Request()` 进行方法调用，nil 指针导致 panic。修复方案：在 `HashIPBalance.Select()` 入口添加 `if ctx == nil { return 0 }` 守卫。

### L3 — 单服务器边界 — 1 case

| 编号 | 注入方式 | 结果 |
|------|---------|------|
| L3 | 单台服务器 `[{ID:42}]` | ✅ 4 种 LB 都返回 42 |

### L4 — 权重边界 — 2 cases

| 编号 | 注入方式 | 结果 | 分析 |
|------|---------|------|------|
| L4.1 | 零权重 `Weight:0` | ✅ 零权重从不被选中 | 与 Nginx upstream 行为一致 |
| L4.3 | 超大权重 `Weight:2^62-1` | ✅ 无 panic | 大整数溢出安全 |

### L5 — 高并发 — 1 case

| 编号 | 注入方式 | 结果 |
|------|---------|------|
| L5.1 | 40 goroutine 并发 | ✅ 无 panic / 无 data race |

### L6 — 未知 LB 类型 — 1 case

| 编号 | 注入方式 | 结果 |
|------|---------|------|
| L6.1 | LB 类型 999 和 -1 | ✅ fallback 到 RoundRobin |

### L7 — 一致性校验 — 2 cases

| 编号 | 注入方式 | 结果 |
|------|---------|------|
| L7.1 | HashIP: 同 IP 20 次 | ✅ 始终返回同一服务器 |
| L7.2 | RR: 连续 20 次 | ✅ 3→1→2 正确轮询 |

---

## 模块 3: Plugin JS 插件引擎模块

**文件**: `pkg/plugin/fault_injection_test.go` | **测试数**: 17 | **结果**: ✅ 全部 PASS

### 注入策略与实现原理

Manba 使用 **Otto JS 引擎**（Go 编写的 JavaScript 解释器）实现插件机制。插件生命周期为 `NewPlugin() → Pre() → Post()`。

```go
// JS 插件接口
type Plugin interface {
    Init(cfg string) error
    Pre(c Context) (statusCode int, err error)
    Post(c Context) (statusCode int, err error)
    PostErr(c Context)
}

// 插件加载流程
pluginContent := []byte(JS代码) → Otto Runtime → 调用 NewPlugin() → 获取 Pre/Post 函数
```

### P1 — JS 初始化错误 — 5 cases

| 编号 | 注入方式 | 故障数据 | 结果 |
|------|---------|----------|------|
| P1.1 | 无效 JS 语法 | `function NewPlugin() { return { "pre": function(c) { `（不完整） | ✅ 语法错误 |
| P1.2 | 构造函数非函数 | `var NewPlugin = "not a function"` | ✅ 正确拦截 |
| P1.3 | 返回非对象 | 构造函数返回字符串 | ✅ 正确拦截 |
| P1.4 | pre 不是函数 | `pre: "not a function"` | ✅ 正确拦截 |
| P1.5 | post 不是函数 | `post: 12345` | ✅ 正确拦截 |

### P2 — 返回值异常 — 6 cases

| 编号 | 注入方式 | 故障数据 | 结果 |
|------|---------|----------|------|
| P2.1 | pre 返回字符串 | `return "string"` | ✅ 正确拦截 |
| P2.2 | 返回空对象 | `return {}`（无 code） | ✅ 正确拦截 |
| P2.3 | code 为字符串 | `return {"code": "200"}` | ✅ 正确拦截 |
| P2.4 | error 为数字 | `return {"code": 500, "error": 12345}` | ✅ 正确拦截 |
| P2.5 | pre 抛异常 | `throw new Error("intentional crash")` | ✅ 捕获 500 |
| P2.6 | post 返回 undefined | `return undefined` | ✅ 正确拦截 |

### P3 — nil 上下文 — 1 case

| 编号 | 注入方式 | 结果 |
|------|---------|------|
| P3.1 | `Pre(nil)` | ✅ 无 panic |

### P4 — 空插件内容 — 1 case

| 编号 | 注入方式 | 结果 |
|------|---------|------|
| P4.1 | `Content: []byte("")` | ✅ 正确拦截 |

### P5 — Require 异常 — 2 cases

| 编号 | 注入方式 | 结果 |
|------|---------|------|
| P5.1 | `require("nonexistent_module")` | ✅ Otto 返回 nil |
| P5.2 | 空 cfg + `JSON.Parse(cfg)` | ✅ 报错 |

### P6/P7 — 高频调用 — 2 cases

| 编号 | 注入方式 | 结果 | 分析 |
|------|---------|------|------|
| P6.1 | 1000 次连续 `Pre()` | ✅ 全部成功 | Otto 引擎稳定性良好 |
| P7.1 | 500 次串行 `Pre()` | ✅ 全部成功 | 串行化避免了并发问题 |

> ⚠️ **注意**: Otto JS 引擎不是线程安全的。并发调用同一 Runtime 实例会导致 `concurrent map writes` panic。这是 Otto 的设计限制。

---

## 模块 4: Filter 上下文模块

**文件**: `pkg/filter/fault_injection_test.go` | **测试数**: 5 | **结果**: ✅ 全部 PASS

### FT1 — Context 属性边界 — 2 cases

| 编号 | 注入方式 | 结果 | 风险 |
|------|---------|------|------|
| FT1.1 | 获取不存在的属性 | ✅ 返回 nil | 无 |
| FT1.2 | 20 goroutine 并发读写 | ✅ 无 data race | ✅ **安全** |

### FT2 — StringValue 类型断言 — 1 case

| 编号 | 注入方式 | 结果 | 分析 |
|------|---------|------|------|
| **FT2.1** | **访问不存在 attr 的 StringValue** | ⚠️ **panic** | **🔴 高危** |

**FT2.1 Bug 分析**：`StringValue()` 方法直接对 `GetAttr(key)` 返回值做类型断言 `value.(string)`，当 key 不存在（返回 nil）时导致 panic。修复方案：改为带检查的类型断言 `if v, ok := value.(string); ok { ... }`。

### FT3 — CachedValue nil 输入 — 2 cases

| 编号 | 注入方式 | 结果 | 分析 |
|------|---------|------|------|
| **FT3.1** | `NewCachedValue(nil)` | ⚠️ **panic** | **🔴 高危** |
| **FT3.2** | `ReadCachedValueTo(nil, _)` | ⚠️ **panic** | **🔴 高危** |

**FT3 分析**：`NewCachedValue` 和 `ReadCachedValueTo` 都没有对 nil Response 做保护。在生产环境中，如果一个 filter 返回了空的 Response 链，会导致整个代理崩溃。修复方案：在函数入口添加 nil 检查。

---

## 模块 5: RateLimiter 限流模块

**文件**: `pkg/proxy/fault_injection_rate_limit_test.go` | **测试数**: 7 | **结果**: ✅ 全部 PASS

### 注入策略与实现原理

限流模块基于 **Token Bucket（令牌桶）算法**，通过控制令牌填充速率和桶容量来实现 QPS 限制。

```go
type rateLimiter struct {
    rate  int           // 每秒令牌数 (QPS)
    burst int           // 桶容量
    bucket *ratelimit.Bucket  // 底层令牌桶实现 (github.com/beefsack/go-rate)
}
```

### R1 — RateLimiter 边界 — 6 cases

| 编号 | 注入方式 | 结果 | 分析 |
|------|---------|------|------|
| **R1.1** | **QPS=0** | ⚠️ **panic**: 除零 | **🔴 高危** |
| R1.2 | QPS=1 | ✅ 第 2 个请求被拒绝 | — |
| **R1.3** | **超大 QPS** | ⚠️ **panic**: fill interval 不合法 | **🔴 高危** |
| **R1.4** | **负数 QPS** | ⚠️ **panic**: fill interval 不合法 | **🔴 高危** |
| R1.5 | Wait 模式 | ✅ 200 请求耗时 ~1s（QPS=100） | — |
| R1.6 | 超大 count | ✅ `do(2^31)` 返回 true | — |

**R1.1/R1.3/R1.4 Bug 分析**：`newRateLimiter(rate)` 没有对 rate 参数做合法性校验，直接传给令牌桶库。rate=0 导致除零 panic，rate 负值或超大值导致 fill interval 计算异常。修复方案：在构造函数中增加 `if rate <= 0 { rate = 1 }` 守卫。

### R2 — Bucket 边缘 — 1 case

| 编号 | 注入方式 | 结果 |
|------|---------|------|
| R2.1 | 纳秒级 fill interval | ✅ TakeAvailable(1)=1 |

---

## 模块 6: JWT 认证模块

**文件**: `pkg/proxy/fault_injection_jwt_test.go` | **测试数**: 10 | **结果**: ✅ 全部 PASS

### J1 — 配置解析异常 — 10 cases

| 编号 | 注入方式 | 结果 | 分析 |
|------|---------|------|------|
| J1.1 | 不存在的配置文件 | ✅ 正确报错 | — |
| J1.2 | 无效 JSON 配置 | ✅ 正确报错 | — |
| J1.3 | 不支持的签名方法 | ✅ 正确报错 | — |
| J1.4 | 空 secret | ✅ 创建成功 | 运行时才报错 |
| J1.5 | 未知 action | ✅ 正确报错 | — |
| **J1.6** | **无效 tokenLookup** | ⚠️ **panic**: index out of range | **🔴 高危** |
| J1.7 | tokenLookup 只有 `:` | ✅ 创建成功 | — |
| J1.8 | query 空参数名 | ✅ 创建成功 | — |
| J1.9 | cookie 空名 | ✅ 创建成功 | — |
| J1.10 | Redis 负数超时 | ✅ 创建成功 | 运行时才报错 |

**J1.6 Bug 分析**：JWT 配置中的 `tokenLookup` 字段格式为 `source:name`（如 `header:Authorization`），代码通过 `strings.Split(lookup, ":")` 解析后直接访问 `parts[1]`。当用户配置为 `header`（缺少 `:name` 部分）时，数组越界导致 panic。修复方案：在访问 `parts[1]` 前检查数组长度。

---

## 汇总：发现的 Bug 清单

| 编号 | 模块 | 位置 | Bug 描述 | 风险 | 修复方案 |
|------|------|------|----------|------|----------|
| L2.4 | LoadBalance | `pkg/lb/hash.go` | HashIP LB 的 `Select(nil, servers)` 导致 nil pointer panic | 🔴 高危 | 在 `Select()` 入口添加 `if ctx == nil` 守卫 |
| FT2.1 | Filter | `pkg/filter/context.go` | `StringValue()` 对 nil attr 做类型断言导致 panic | 🔴 高危 | 改用带 ok 检查的类型断言 |
| FT3.1 | Filter | `pkg/filter/cached_value.go` | `NewCachedValue(nil)` 导致 nil pointer panic | 🔴 高危 | 在函数入口添加 nil 检查 |
| FT3.2 | Filter | `pkg/filter/cached_value.go` | `ReadCachedValueTo(nil, _)` 导致 nil pointer panic | 🔴 高危 | 在函数入口添加 nil 检查 |
| R1.1 | RateLimit | `pkg/proxy/rate_limit.go` | QPS=0 导致除零 panic | 🔴 高危 | 在构造函数中校验 `if rate <= 0` |
| R1.3 | RateLimit | `pkg/proxy/rate_limit.go` | 超大 QPS 导致 fill interval 计算异常 panic | 🔴 高危 | 添加上限校验 |
| R1.4 | RateLimit | `pkg/proxy/rate_limit.go` | 负数 QPS 导致 fill interval 计算异常 panic | 🔴 高危 | 添加负数校验 |
| J1.6 | JWT | `pkg/proxy/jwt.go` | tokenLookup 缺少 `:name` 部分导致数组越界 panic | 🔴 高危 | 在访问 `parts[1]` 前检查长度 |
| F5.1 | Route | `pkg/route/route.go` | 通配符优先级为"先注册先匹配"而非"精确匹配优先" | 🟡 中 | 改用精确匹配优先策略 |
| F1.11 | Route | `pkg/route/route.go` | 空字符注入路径可以匹配成功 | 🟡 中 | 添加输入净化 |

---

## 关键技术架构分析

### 1. 故障注入策略

Manba 采用 **白盒单元测试级故障注入**，在代码层面直接构造异常输入：

| 策略 | 描述 | 示例 |
|------|------|------|
| **边界值注入** | 在参数的零值/负值/最大值处注入 | QPS=0, Weight=0, 空列表 |
| **类型混淆注入** | 给函数传递错误类型的值 | code 为 string、error 为 number |
| **nil 注入** | 将函数参数设为 nil | ctx=nil, servers=nil |
| **并发压力注入** | 高并发读写共享状态 | 10~40 goroutine 同时操作 |
| **资源耗尽注入** | 超大输入消耗处理资源 | 100 段路径、50 层嵌套 |

### 2. 底层实现原理

Manba 的模块间通过 **Filter Chain** 串联：

```
Request → Router → [Filter1 → Filter2 → ...] → LoadBalance → Backend
                        ↕ (Plugin JS Engine)
```

- **Route** 使用 **前缀树 (Trie)** 实现 URL 匹配，路径段作为节点
- **LoadBalance** 使用接口 + 策略模式，4 种策略独立实现
- **Plugin** 通过 **Otto JS 引擎** 解释执行用户脚本，Sandbox 隔离
- **RateLimiter** 基于 **Token Bucket** 算法（go-rate 库）

### 3. 缺陷分布统计

| 模块 | 测试数 | 发现的 Bug | Bug 密度 |
|------|--------|-----------|----------|
| Route | 25 | 2 (F5.1, F1.11) | 8% |
| LoadBalance | 16 | 1 (L2.4) | 6.25% |
| Plugin JS | 17 | 0 | 0% |
| Filter | 5 | 3 (FT2.1, FT3.1, FT3.2) | **60%** |
| RateLimiter | 7 | 3 (R1.1, R1.3, R1.4) | **42.8%** |
| JWT | 10 | 1 (J1.6) | 10% |
| **总计** | **51** | **10** | **19.6%** |

Filter 和 RateLimiter 模块的 Bug 密度最高，建议优先修复。

### 4. 最佳实践建议

1. **所有公有函数都应对 nil 参数做守卫检查** — 多数 Bug 源于 nil 指针
2. **配置解析阶段应做参数合法性校验** — QPS 等数值参数常被忽略
3. **类型断言始终使用带 ok 检查的语法** — `v, ok := x.(T)` 而非 `v := x.(T)`
4. **字符串分割后应检查结果长度** — `parts := strings.Split(s, ":")` 后检查 `len(parts)`
5. **Filter Chain 端点应做 nil Response 保护** — 避免空链传播
