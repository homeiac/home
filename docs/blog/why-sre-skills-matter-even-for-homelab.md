# Why SRE Skills Matter Even for Homelab (And Why "It Just Works" Doesn't)

*Or: The Two Lines of Code That Even an AI Missed*

## The Setup

I have a homelab. Kubernetes cluster, Frigate NVR for cameras, the works. I had Claude (yes, the AI) write a health checker that monitors Frigate and restarts it if something goes wrong. Simple CronJob, runs every 5 minutes, sends me an email if it has to restart things.

The code worked. Tests passed. Deployed to prod. The AI was very pleased with itself.

Then my node went down for maintenance.

## The Alert Storm

My phone buzzed. Email: "Frigate Restarted."

Five minutes later: "Frigate Restarted."

Five minutes later: "Frigate Restarted."

The health checker was doing exactly what I told it to do. Frigate was unhealthy (because the node was down), so it kept trying to restart it and kept telling me about it. Every. Five. Minutes.

## What Was Missing

Two things, both obvious in hindsight:

### 1. Alert Deduplication

The checker had no memory. It didn't know it had already told me about this incident. Every run was a fresh start, a new discovery, a new notification.

The fix was trivial - a single field in a ConfigMap:

```yaml
alert_sent_for_incident: "false"
```

Set it to `true` when you send an alert. Reset it to `false` when the service recovers. Don't send another alert if it's already `true`.

### 2. Precondition Checking

The checker was trying to restart a pod on a node that was down. This is like trying to start a car with no engine. The restart would "succeed" (kubectl accepts the command), but the pod would just sit in Pending forever.

The fix was also trivial:

```bash
NODE_READY=$(kubectl get node "$NODE" -o jsonpath='{...Ready...}')
if [[ "$NODE_READY" != "True" ]]; then
  echo "Node down, skipping restart"
  exit 0
fi
```

## The Point

These fixes are maybe 15 lines of code combined. A junior developer could write them in 10 minutes once told what to write. An AI could generate them in seconds - once told they were needed.

But knowing they were needed? That's the hard part.

Claude wrote a perfectly functional health checker. It had rate limiting, circuit breakers, consecutive failure thresholds. It looked professional. It would pass a code review.

And it completely missed these two basic failure modes because:

- It had never been woken up at 3 AM by alert storms
- It had never watched dashboards turn red because automation tried to fix things that couldn't be fixed
- It had never lived through the pain that teaches you these patterns
- It optimized for the happy path because that's what the requirements described

The human looked at it and said "what happens when still-fawn is down?" The AI hadn't thought to ask.

## Why "Managed Services" Don't Teach This

Here's my hot take: if you've only ever used managed Kubernetes (AKS, EKS, GKE), you might never learn this stuff.

When your node goes down in AKS, Microsoft's control plane handles it. The node gets replaced. Your pods reschedule. You maybe get a single, deduplicated alert from Azure Monitor that says "node was unhealthy, we fixed it."

You don't see:

- The state machine that tracks incident lifecycle
- The precondition checks before every remediation action
- The rate limiting that prevents thrashing
- The circuit breakers that stop cascading failures

It "just works." Until you try to build something yourself and realize you don't know why it works.

## The Homelab Advantage

My janky CronJob taught me more about SRE in one afternoon than a year of clicking through Azure Portal ever did.

I had to think about:

- **State management**: What does the system need to remember between runs?
- **Failure modes**: What happens when the thing I'm trying to fix can't be fixed?
- **Idempotency**: Can I run this action multiple times safely?
- **Observability**: How do I know what the automation actually did?

These are the questions that separate "I deployed a Kubernetes cluster" from "I understand distributed systems."

## The Uncomfortable Truth

Cloud providers have made infrastructure so easy that we've created a generation of engineers who've never had to think about why things are built the way they are. And now AI can generate the code for you too.

Auto-scaling? Click a checkbox. Or ask Claude.
High availability? Select multiple zones. Or ask Claude.
Alerting? Enable the default dashboard. Or ask Claude to write a health checker.

And it works! Until your node goes down. Until your automation makes things worse. Until you need someone who's felt the pain to look at the code and ask "but what happens when..."

The AI gave me working code. The human asked the right question.

## What To Do About It

Run a homelab. Or at least, run something where you're responsible for the failure modes.

Not because managed services are bad - they're great, use them in production. But because you need to understand what they're doing for you. You need to feel the pain of an alert storm to understand why PagerDuty has incident deduplication. You need to watch a restart loop to understand why Kubernetes has backoff timers.

The cloud abstracts away the hard problems. That's the product. But if you want to be an SRE, you need to have solved those problems at least once yourself.

Otherwise, you're just a very expensive button clicker. Or worse - someone who blindly trusts AI-generated code because it "looks right."

## The Fixes

For the curious, here's what I added:

**Alert deduplication** (ConfigMap + logic):
```yaml
data:
  alert_sent_for_incident: "false"
```

```bash
if [[ "$ALERT_SENT" == "true" ]]; then
  echo "Alert already sent - skipping"
else
  send_email
  kubectl patch cm ... alert_sent_for_incident="true"
fi

# On recovery:
kubectl patch cm ... alert_sent_for_incident="false"
```

**Node availability check**:
```bash
NODE_READY=$(kubectl get node "$NODE" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')
if [[ "$NODE_READY" != "True" ]]; then
  echo "Node down - skipping restart"
  exit 0
fi
```

15 lines. And a human who knew to ask for them.

---

*Tags: sre, homelab, kubernetes, alerting, cloud, aks, ai, claude, learning, career*
