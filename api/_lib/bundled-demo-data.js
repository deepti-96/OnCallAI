export const BUNDLED_LOGS = {
  db: [
    {
      file_name: "2025-09-27T11-02Z.log",
      snippet:
        "2025-09-27T11:02:01Z ERROR db-conn: connection refused to postgres:5432\n2025-09-27T11:02:02Z WARN retrying...\n",
    },
  ],
  infra: [
    {
      file_name: "2025-09-27T10-55Z.log",
      snippet: "2025-09-27T10:55:12Z kubelet: OOMKilled container payment-service\n",
    },
  ],
  web: [
    {
      file_name: "2025-09-27T10-40Z.log",
      snippet:
        "2025-09-27T10:40:01Z GET /checkout 500\n2025-09-27T10:40:02Z java.lang.NullPointerException at com.app.Payments...\n",
    },
  ],
};

export const BUNDLED_RAG_EXAMPLES = [
  {
    pattern: "connection refused|ECONNREFUSED",
    root_cause: "DB pod crashed / not ready",
    mitigation: ["Restart DB pod", "Increase memory"],
  },
  {
    pattern: "OOMKilled|OutOfMemoryError",
    root_cause: "Service OOM",
    mitigation: ["Increase memory limit", "Investigate leak"],
  },
  {
    pattern: "HTTP 500|NullPointerException",
    root_cause: "App bug/null deref",
    mitigation: ["Rollback", "Add null checks"],
  },
];
