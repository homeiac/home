Title: Pushing CI/CD to the Edge: Scaling Windows Workloads on Kubernetes / Kubernetes Edge with KEDA/Flux

Description:
Over 70 % of on-prem enterprise workloads still run on Windows Server, yet Windows apps remain second-class citizens in Kubernetes. This talk shows how BD pushed CI/CD to the edge by replacing a few hand-crafted Windows VMs with hundreds of Windows-container Azure DevOps agents on AKS Edge Essentials.

Using KEDA for event-driven autoscaling and seamless cloud-bursting to AKS, we:

    boosted build success 70 % → 99.9 %

    cut queue time hours → seconds

    slashed agent rollout weeks → minutes

The same images launch throw-away demo/test stacks in seconds, power AI-driven test loops. All this done cost effectively that we recouped our on-prem costs in a quarter.

A live demo walks through GitOps manifests, on-demand provisioning, and KEDA scaling logic. Attendees leave with a ready-to-apply blueprint for giving Windows/.NET workloads first-class, cloud-native status—cost-efficient at the edge, elastic in the cloud, and primed for faster, AI-enabled developer feedback.


