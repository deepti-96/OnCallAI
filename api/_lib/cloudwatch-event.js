function buildAlarmArn({ region, accountId, alarmName }) {
  return `arn:aws:cloudwatch:${region}:${accountId}:alarm:${alarmName}`;
}

function buildStateReason({ scenario, occurrenceCount, severity }) {
  return `${scenario.metricName} breached threshold ${scenario.threshold} for ${occurrenceCount} evaluation signal(s); severity=${severity}.`;
}

export function buildCloudWatchEvent({ scenario, incident, occurrenceCount, severity }) {
  const region = scenario.awsRegion || "us-east-1";
  const accountId = scenario.awsAccountId || "123456789012";
  const eventTime = incident.created_at;

  return {
    source: "aws.cloudwatch",
    account: accountId,
    region,
    time: eventTime,
    detailType: "CloudWatch Alarm State Change",
    resources: [buildAlarmArn({ region, accountId, alarmName: scenario.alarmName })],
    detail: {
      alarmName: scenario.alarmName,
      alarmDescription: scenario.summary,
      awsAccountId: accountId,
      state: {
        value: incident.alert_state,
        reason: buildStateReason({ scenario, occurrenceCount, severity }),
        timestamp: eventTime,
      },
      previousState: {
        value: incident.alert_state === "OK" ? "ALARM" : "INSUFFICIENT_DATA",
        reason: "Previous state simulated for hosted incident replay.",
        timestamp: eventTime,
      },
      configuration: {
        description: scenario.title,
        metrics: [
          {
            id: "m1",
            metricStat: {
              metric: {
                namespace: scenario.metricNamespace,
                name: scenario.metricName,
                dimensions: scenario.dimensions || [],
              },
              period: 60,
              stat: "Average",
              unit: scenario.metricUnit || "Count",
            },
            returnData: true,
          },
        ],
      },
    },
  };
}

export function buildCloudWatchLogSource({ scenario }) {
  return {
    log_group: scenario.cloudWatchLogGroup,
    stream_prefix: scenario.cloudWatchStreamPrefix,
    region: scenario.awsRegion || "us-east-1",
  };
}
