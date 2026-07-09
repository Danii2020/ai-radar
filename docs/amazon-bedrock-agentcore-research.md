# Amazon Bedrock AgentCore — Research Overview

> Research date: 2026-06-02  
> Sources: AWS official docs, Context7, AWS blog posts, CloudBurn, community deep-dives

---

## 1. What Is It?

Amazon Bedrock AgentCore is a **fully managed infrastructure platform** for building, deploying, and operating AI agents at production scale. It is NOT a framework (like LangGraph or CrewAI) — it is the **infrastructure layer** on which any agent framework can run.

Key value proposition:
- Zero infrastructure management (no EC2, ECS, K8s to operate)
- Enterprise-grade security by default (IAM, microVM isolation, policy enforcement)
- Framework-agnostic — works with Strands, LangGraph, CrewAI, LlamaIndex, or custom code
- Model-agnostic — any foundation model accessible via Bedrock or direct API

---

## 2. Core Service Components

### 2.1 AgentCore Runtime

The execution backbone of the platform.

- Each agent session runs in a **dedicated microVM** with isolated CPU, memory, and filesystem
- Sessions run up to **8 hours** and can suspend and resume mid-task (human-in-the-loop support)
- After session end, the entire microVM is terminated and memory sanitized (deterministic security)
- Handles the full **agent loop**: reasoning → tool selection → action execution → response streaming
- Auto-scales with no infrastructure management required
- Exposes a `BedrockAgentCoreApp` Python class as the entry point

```python
from bedrock_agentcore.runtime import BedrockAgentCoreApp

app = BedrockAgentCoreApp()
```

### 2.2 Managed Harness

A higher-level abstraction on top of Runtime. You declare a model, system prompt, and list of tools — the harness manages the agent loop automatically, with no orchestration code required.

```python
response = client.invoke_harness(
    harnessArn=HARNESS_ARN,
    runtimeSessionId=SESSION_ID,
    tools=tools,
    messages=[{"role": "user", "content": [{"text": "Find a keyboard under $200 and request approval."}]}]
)
```

Supported tool types in harness:
- `remote_mcp` — any remote MCP server (with or without auth headers)
- `agentcore_gateway` — AgentCore Gateway (SigV4 or OAuth)
- `agentcore_browser` — managed browser
- `agentcore_code_interpreter` — sandboxed code execution
- `inline_function` — client-side human-in-the-loop tools

### 2.3 Memory

Two layers of memory with clear separation:

| Layer | Name | Purpose |
|---|---|---|
| Short-term | STM | In-session context, raw events, conversation turns |
| Long-term | LTM | Cross-session intelligence, episodic learning, extracted insights |

A **memory resource** is the logical container that defines retention policies, security, and transformation strategies (how raw events become long-term insights).

```python
from bedrock_agentcore.memory import MemoryClient

memory_client = MemoryClient(region_name='us-west-2')
MEMORY_ID = os.getenv('MEMORY_ID')
```

Key constraints:
- Events cannot expire in less than **7 days**
- No force-expire for events set at 30 or 90 days — set `EventExpirationDuration` explicitly at creation
- STM and LTM can be used independently or together

### 2.4 Gateway

Connects agents to real-world systems by turning APIs, Lambda functions, and external services into agent-callable tools automatically.

- Supports SigV4 auth (default) and OAuth
- Handles managed credential rotation
- Exposes tools over MCP-compatible interface
- Can proxy third-party MCP servers behind a secure boundary
- VPC-compatible (watch for cross-AZ egress costs)

```python
{
    "type": "agentcore_gateway",
    "name": "my-gateway",
    "config": {
        "agentCoreGateway": {
            "gatewayArn": "arn:aws:bedrock-agentcore:us-west-2:123456789012:gateway/my-gateway"
        }
    }
}
```

### 2.5 Identity

Manages how agents authenticate to external systems and services.

- Creates **workload identities** (ARN-based) for agents
- Integrates natively with AWS services via IAM
- Connects to third-party identity providers: **Okta, Entra (Azure AD), Amazon Cognito**
- Connects to third-party apps: **Slack, Zoom**
- Stores credentials in **Token Vault** (API keys referenced by ARN, not hardcoded)
- Credentials resolved at invocation time — agents never touch raw secrets

```python
from bedrock_agentcore.services.identity import IdentityClient

identity_client = IdentityClient("us-east-1")
response = identity_client.create_workload_identity(name='my-python-agent')
agent_arn = response['workloadIdentityArn']
```

Token Vault reference pattern:
```
"x-api-key": "${arn:aws:bedrock-agentcore:us-west-2:123456789012:token-vault/default/apikeycredentialprovider/my-key}"
```

### 2.6 Code Interpreter

Sandboxed, managed environment for agents to write and run code safely.

- Supports Python (primary)
- Isolated execution — no risk of agent code escaping to host
- Improves agent accuracy for computational/analytical tasks
- Session-based: `start()` → `invoke()` → `stop()`

```python
from bedrock_agentcore.tools.code_interpreter_client import CodeInterpreter

code_client = CodeInterpreter('us-west-2')
code_client.start()
response = code_client.invoke("executeCode", {
    "language": "python",
    "code": 'print("Hello World")'
})
code_client.stop()
```

### 2.7 Browser (Managed Cloud Browser)

Gives agents the ability to browse the web in a managed, isolated cloud browser.

- Session-based browser with live view streaming
- Supports automation stream (Playwright-style actions) and live view stream (visual inspection)
- Browser profiles (cookies, localStorage) are persisted in S3
- Requires explicit IAM permissions (`bedrock-agentcore:StartBrowserSession`, etc.)

### 2.8 Observability & Evaluations

- Built-in trace collection for agent sessions
- **Batch evaluations** — run quality checks offline against recorded sessions
- **A/B tests** — compare two agent versions in production
- Recommendation engine for improvement
- Completes the observe → evaluate → improve loop
- **No free tier** for observability — use percentage-based sampling in high-traffic production

---

## 3. Developer Experience

### CLI & SDK

```bash
# Install
pip install bedrock-agentcore bedrock-agentcore-starter-toolkit boto3 strands-agents

# Deploy an agent
agentcore deploy

# Check status
agentcore status
# Shows: Memory ID, Memory Type (STM / STM+LTM), Observability status
```

The CLI handles:
- Building and pushing agent container images to ECR
- Creating the Runtime instance
- Auto-wiring IAM permissions for Identity, Gateway access tokens, etc.

### Framework Integrations

AgentCore is tested and documented with:
- **Strands Agents** (AWS-native, recommended starting point)
- **LangGraph**
- **CrewAI**
- **LlamaIndex**
- Custom Python agents

---

## 4. Security Model

| Layer | Mechanism |
|---|---|
| Session isolation | Per-session microVM (CPU, memory, filesystem separated) |
| Policy enforcement | Deterministic controls outside agent code — blocks unauthorized actions in real time |
| Credential handling | Token Vault — secrets referenced by ARN, resolved at runtime |
| IAM integration | Full AWS IAM for access control to all AgentCore services |
| Auth to external services | SigV4, OAuth, Okta, Entra, Cognito |
| Post-session cleanup | MicroVM terminated and memory sanitized |

---

## 5. Pricing Model

Consumption-based, no upfront commitment. 12 independent billing components across 5 patterns:

| Component | Billing Pattern | Notes |
|---|---|---|
| Runtime (Harness) | Free (pay for underlying resources) | Harness itself has no surcharge |
| Runtime compute | Per-second, 1s minimum, 128 MB minimum | Only billed for **active** computation, not I/O wait |
| Code Interpreter | Per-session active consumption | Significant savings since agents spend 30–70% in I/O wait |
| Browser profiles | S3 Standard rates | Billed for stored browser profile data |
| Gateway VPC egress | $0.006/GB | Cross-AZ transfer at standard EC2 rates |
| Evaluations/Observability | Per-request, no free tier | Use sampling to control costs at scale |
| Memory | Per-record | Retention minimums apply (7-day floor) |

---

## 6. Service Quotas & Hard Limits

- **149 total quotas**, 94 of which are adjustable via AWS Support
- All quotas are **region-specific**
- Non-adjustable limits:
  - 200,000 input tokens per minute
  - 100 evaluations per minute (built-in evaluators)
- Session duration maximum: **8 hours**
- Memory event expiration minimum: **7 days**

---

## 7. Trade-offs & Limitations

### Advantages
| Strength | Detail |
|---|---|
| Zero infra management | No ECS, EC2, Kubernetes to configure or operate |
| Enterprise security out-of-the-box | MicroVM isolation, IAM, Token Vault, policy enforcement |
| Human-in-the-loop support | Sessions suspend/resume; inline function tools for approval flows |
| Framework agnostic | Bring any Python agent framework |
| Model agnostic | Any Bedrock-accessible model or external model API |
| Managed credential rotation | Gateway handles OAuth refresh; no manual rotation |
| Built-in observability | Traces, evals, A/B testing without third-party tooling |

### Limitations & Risks
| Limitation | Impact |
|---|---|
| **AWS lock-in** | Deep coupling to IAM, ECR, VPC, S3, Bedrock — migrating out is costly |
| **Memory retention floors** | Cannot expire events in < 7 days; no force-expire for 30/90-day events |
| **Observability has no free tier** | High-traffic agents must implement sampling to avoid uncapped charges |
| **VPC networking cost surprises** | PrivateLink + cross-AZ transfer can appear as unexplained bills |
| **MicroVM overhead** | Per-session VM spin-up adds latency for very short-lived agent calls |
| **Token rate limits** | 200K input tokens/min hard non-adjustable — multi-tenant high-volume apps may hit this |
| **Region availability** | Not all AWS regions supported; check regional availability before designing architecture |
| **Container-based deployment** | Agent code must be containerized — adds build/push step to deployment pipeline |

---

## 8. When to Use AgentCore (vs. Alternatives)

### Use AgentCore when:
- Already committed to AWS ecosystem (other Bedrock services, IAM, S3, Lambda)
- Need production-grade managed infrastructure without a dedicated DevOps team
- Security and compliance requirements are strict (SOC 2, IAM-native, session isolation)
- Agents need to authenticate to multiple external services with managed credential rotation
- Want built-in observability and A/B evaluation without third-party tooling

### Consider alternatives when:
- **Multi-cloud or cloud-agnostic** is a hard requirement (LangGraph + self-hosted is more portable)
- **Complex multi-agent orchestration with explicit state machines** is core — LangGraph's graph model is more expressive
- **Role-based collaborative agents** — CrewAI's team model fits better
- Need maximum control over infrastructure topology or container runtime
- Very short-lived, low-latency agent calls where microVM spin-up is prohibitive

### The 2026 Gold Standard Pattern
Use AgentCore as the **Infrastructure Layer** + LangGraph/CrewAI/Strands as the **Logic Layer**. They are complementary, not competing.

---

## 9. Key SDK Packages

| Package | Purpose |
|---|---|
| `bedrock-agentcore` | Core Python SDK (runtime, memory, identity, tools) |
| `bedrock-agentcore-starter-toolkit` | CLI (`agentcore deploy/status`), scaffolding, quickstarts |
| `strands-agents` | AWS-native agent framework, best integrated with AgentCore |
| `boto3` | AWS SDK for lower-level resource management |

---

## 10. Useful References

- [AgentCore Product Page](https://aws.amazon.com/bedrock/agentcore/)
- [Official Developer Guide](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)
- [AgentCore Pricing](https://aws.amazon.com/bedrock/agentcore/pricing/)
- [Service Quotas & Limits](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html)
- [Starter Toolkit Docs](https://aws.github.io/bedrock-agentcore-starter-toolkit/)
- [AgentCore Samples (awslabs)](https://github.com/awslabs/agentcore-samples)
- [Runtime: Host agents and tools](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agents-tools-runtime.html)
- [Memory: Building context-aware agents](https://aws.amazon.com/blogs/machine-learning/amazon-bedrock-agentcore-memory-building-context-aware-agents/)
- [AWS Prescriptive Guidance: Comparing agentic AI frameworks](https://docs.aws.amazon.com/prescriptive-guidance/latest/agentic-ai-frameworks/comparing-agentic-ai-frameworks.html)
