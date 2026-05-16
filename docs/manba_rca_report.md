# Manba API Gateway 故障诊断报告

## 诊断概要

基于 Manba 故障注入测试套件的实际运行结果，选取两个高危故障进行根因分析。

---

## 样例 1：HashIP 负载均衡器 nil 上下文崩溃

### 故障概览

| 项目 | 内容 |
|------|------|
| 故障编号 | L2.4 |
| 故障标题 | HashIP 负载均衡器在 nil 请求上下文下 panic 崩溃 |
| 影响范围 | 使用 HashIP 策略的 API 路由，整个代理进程 |
| 故障类型 | Go 运行时 nil pointer dereference |
| 根因置信度 | 🟢 高 |

### 故障复现过程

测试代码调用负载均衡器的 `Select()` 方法，传入 nil 作为 Context：

```go
// pkg/lb/fault_injection_test.go
func TestFaultInjection_LB_NilCtx_HashIP(t *testing.T) {
    servers := []metapb.Server{{ID: 19, Weight: 100}}
    lb := NewLoadBalance(HashIP)
    id := lb.Select(nil, servers)  // ctx = nil
}
```

### 实际运行输出

```
[L2.4 Hash] nil ctx HashIP -> panic: runtime error: invalid memory address or nil pointer dereference
```

### 根因分析

#### 故障传导链

```
外部调用 Select(nil, servers)
    │
    ▼
HashIPBalance.Select() 获取客户端 IP
    │
    ▼
util.ClientIP(ctx) 内部调用 ctx.Request()
    │                        ↕ ctx = nil
    ▼
nil.Request() → runtime error: invalid memory address or nil pointer dereference
    │
    ▼
🔴 整个代理进程 crash
```

#### 代码定位

```go
// pkg/lb/hash.go (反编译推断)
func (lb *HashIPBalance) Select(ctx Context, servers []metapb.Server) int {
    clientIP := util.ClientIP(ctx)  // ← ctx 未做 nil 检查
    // ...使用 clientIP 做哈希
}
```

```go
// util 层
func ClientIP(ctx Context) string {
    return ctx.Request().Header.ClientIP()  // ← nil.Request() → panic
}
```

#### 证据链

| 证据 | 说明 | 来源 |
|------|------|------|
| Random LB nil ctx | ✅ 正常运行，无 panic | `fault_injection_test.go` |
| RoundRobin LB nil ctx | ✅ 正常运行，无 panic | `fault_injection_test.go` |
| Weighted Robin LB nil ctx | ✅ 正常运行，无 panic | `fault_injection_test.go` |
| **HashIP LB nil ctx** | **❌ panic** | **`fault_injection_test.go:115`** |

### 影响评估

| 维度 | 评估 |
|------|------|
| **严重程度** | 🔴 P0 — 进程级崩溃 |
| **触发条件** | 只要 `Select()` 收到 nil ctx 就立即崩溃 |
| **利用难度** | 🟢 低 — 不需要特殊权限，只需构造特定请求 |
| **修复优先级** | 🚨 立即 |

### 修复方案

```go
// pkg/lb/hash.go
func (lb *HashIPBalance) Select(ctx Context, servers []metapb.Server) int {
    if ctx == nil {             // ← 添加守卫
        return 0
    }
    clientIP := util.ClientIP(ctx)
    // ...
}
```

或者更彻底的方案，在 `util.ClientIP` 层做保护：

```go
func ClientIP(ctx Context) string {
    if ctx == nil {
        return ""
    }
    return ctx.Request().Header.ClientIP()
}
```

---

## 样例 2：RateLimiter QPS=0 配置除零崩溃

### 故障概览

| 项目 | 内容 |
|------|------|
| 故障编号 | R1.1 |
| 故障标题 | RateLimiter 在 QPS=0 时触发整数除零 panic |
| 影响范围 | 所有使用 RateLimiter 的 API 路由 |
| 故障类型 | Go 运行时 integer divide by zero |
| 根因置信度 | 🟢 高 |

### 故障复现过程

```go
// pkg/proxy/fault_injection_rate_limit_test.go
func TestFaultInjection_RateLimit_ZeroQPS(t *testing.T) {
    rl := newRateLimiter(0)  // QPS = 0
    rl.do(context.TODO())    // → panic: integer divide by zero
}
```

### 实际运行输出

```
[R1.1] 故障注入: newRateLimiter(0) -> panic: runtime error: integer divide by zero
```

### 根因分析

#### 故障传导链

```
配置 QPS = 0
    │
    ▼
newRateLimiter(0) 创建令牌桶
    │
    ▼
rate, _ := rate.NewLimiter(rate.Limit(0), burst)  // fill interval = 0
    │
    ▼
底层令牌桶计算 fill interval: 每秒 / 0 = 无穷大 / 除零
    │
    ▼
🔴 除零 panic，调用进程崩溃
```

#### 代码定位

```go
// pkg/proxy/rate_limit.go
func newRateLimiter(rate int) *rateLimiter {
    return &rateLimiter{
        rate:   rate,
        bucket: rate.NewLimiter(rate.Limit(rate), burst), // ← rate=0 导致除零
    }
}
```

#### 关联故障

| 编号 | 注入方式 | 结果 | 根因 |
|------|---------|------|------|
| **R1.1** | **QPS=0** | **panic: 除零** | **未校验 rate 参数** |
| R1.3 | 超大 QPS | panic: fill interval 不合法 | 未校验 rate 上限 |
| R1.4 | 负数 QPS | panic: fill interval 不合法 | 未校验 rate 下限 |

#### 证据链

| 证据 | 说明 | 来源 |
|------|------|------|
| QPS=1 | ✅ 正常运行，第2个请求被限制 | `fault_injection_test.go` |
| **QPS=0** | **❌ panic: 除零** | **`fault_injection_test.go:25`** |
| QPS=2^30 | ✅ do(2^31) 返回 true | `fault_injection_test.go` |

### 影响评估

| 维度 | 评估 |
|------|------|
| **严重程度** | 🔴 P0 — 进程级崩溃 |
| **触发条件** | 配置中 QPS 设置为 0（如动态配置下发错误） |
| **利用难度** | 🟢 低 — 管理员误配或配置注入攻击 |
| **修复优先级** | 🚨 立即 |

### 修复方案

```go
// pkg/proxy/rate_limit.go
func newRateLimiter(rate int) *rateLimiter {
    if rate <= 0 {              // ← 添加参数校验
        rate = 1                // 默认最小 QPS
    }
    if rate > maxRate {         // ← 上限保护
        rate = maxRate
    }
    return &rateLimiter{
        rate:   rate,
        bucket: rate.NewLimiter(rate.Limit(rate), burst),
    }
}
```

---

## 汇总

| 编号 | 模块 | 故障类型 | 严重程度 | 修复优先级 |
|------|------|----------|----------|-----------|
| L2.4 | LoadBalance HashIP | nil pointer dereference | 🔴 P0 | 🚨 立即 |
| FT2.1 | Filter StringValue | 类型断言 panic | 🔴 P0 | 🚨 立即 |
| FT3.1/3.2 | Filter CachedValue | nil pointer dereference | 🔴 P0 | 🚨 立即 |
| R1.1 | RateLimiter QPS=0 | integer divide by zero | 🔴 P0 | 🚨 立即 |
| R1.3 | RateLimiter 超大 QPS | fill interval 异常 | 🔴 P0 | 🚨 立即 |
| R1.4 | RateLimiter 负数 QPS | fill interval 异常 | 🔴 P0 | 🚨 立即 |
| J1.6 | JWT tokenLookup | index out of range | 🔴 P0 | 🚨 立即 |
| F5.1 | Route 通配符优先级 | 策略设计问题 | 🟡 P2 | 📋 计划 |
| F1.11 | Route 空字符注入 | 输入净化缺失 | 🟡 P3 | 📋 改进 |
