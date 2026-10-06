---
type: llm
---

PASS if the answer labels the Workspace nodes with octelium.com/node-mode-cordium, installs the package with octops install-package octo.example.com --package cordium (and follows the Genesis Job), notes that pre-builds need a CSI driver with VolumeSnapshot support and a VolumeSnapshotClass, and covers giving developers access (a Policy for the Cordium API including WorkspaceService and the console, or equivalent) or DNS/TLS for *.cordium.octo.example.com.
FAIL if it runs octops init or the quick installer on the existing Cluster, or tells the user to edit Cordium-managed Kubernetes objects by hand.
