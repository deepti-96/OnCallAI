#!/usr/bin/env bash
# Create a real CloudWatch -> SNS -> SQS alert path for the OnCallAI demo.
# Everything is named oncallai-demo / oncallai-alarms and fits the AWS free tier.
# Needs the AWS CLI v2 with credentials that can manage logs, cloudwatch, sns, sqs.
# Undo with scripts/aws_demo_teardown.sh
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
export AWS_DEFAULT_REGION="$REGION"
CHECKOUT_GROUP=/oncallai-demo/checkout-service
PAYMENT_GROUP=/oncallai-demo/payment-service
NAME=oncallai-alarms

echo "1/6 log groups (1 day retention)"
for g in "$CHECKOUT_GROUP" "$PAYMENT_GROUP"; do
  aws logs create-log-group --log-group-name "$g" 2>/dev/null || echo "    $g exists"
  aws logs put-retention-policy --log-group-name "$g" --retention-in-days 1
done

echo "2/6 metric filter: every ERROR line in checkout counts 1"
aws logs put-metric-filter \
  --log-group-name "$CHECKOUT_GROUP" \
  --filter-name checkout-errors \
  --filter-pattern '"ERROR"' \
  --metric-transformations metricName=CheckoutErrors,metricNamespace=OnCallAIDemo,metricValue=1,defaultValue=0

echo "3/6 SNS topic and SQS queue"
TOPIC_ARN=$(aws sns create-topic --name "$NAME" --query TopicArn --output text)
QUEUE_URL=$(aws sqs create-queue --queue-name "$NAME" --query QueueUrl --output text)
QUEUE_ARN=$(aws sqs get-queue-attributes --queue-url "$QUEUE_URL" --attribute-names QueueArn \
  --query Attributes.QueueArn --output text)

echo "4/6 let only this topic write to the queue"
ATTRS=$(mktemp)
python3 - "$TOPIC_ARN" "$QUEUE_ARN" > "$ATTRS" <<'PY'
import json, sys
topic, queue = sys.argv[1], sys.argv[2]
policy = {"Version": "2012-10-17", "Statement": [{
    "Effect": "Allow", "Principal": {"Service": "sns.amazonaws.com"},
    "Action": "sqs:SendMessage", "Resource": queue,
    "Condition": {"ArnEquals": {"aws:SourceArn": topic}}}]}
print(json.dumps({"Policy": json.dumps(policy)}))
PY
aws sqs set-queue-attributes --queue-url "$QUEUE_URL" --attributes "file://$ATTRS"
rm -f "$ATTRS"

echo "5/6 subscribe the queue to the topic"
aws sns subscribe --topic-arn "$TOPIC_ARN" --protocol sqs --notification-endpoint "$QUEUE_ARN" >/dev/null

echo "6/6 alarm: 3+ ERROR lines in 60s. Description carries OnCallAI routing hints."
DESC='{"oncallai":{"service":"checkout-service","environment":"prod","log_groups":["/oncallai-demo/checkout-service","/oncallai-demo/payment-service"]}}'
aws cloudwatch put-metric-alarm \
  --alarm-name checkout-service-error-burst \
  --alarm-description "$DESC" \
  --namespace OnCallAIDemo --metric-name CheckoutErrors \
  --statistic Sum --period 60 --evaluation-periods 1 --threshold 3 \
  --comparison-operator GreaterThanOrEqualToThreshold \
  --treat-missing-data notBreaching \
  --alarm-actions "$TOPIC_ARN" --ok-actions "$TOPIC_ARN"

cat <<EOF

Done. Start the console with:

  export AWS_REGION=$REGION
  export CW_SQS_QUEUE_URL=$QUEUE_URL
  python3 -m app.web.server --simulate-mind

Then make checkout fail:

  python3 scripts/aws_emit_logs.py

The alarm usually fires 1 to 3 minutes later. The console picks it up from SQS.
The process needs: sqs:ReceiveMessage, sqs:DeleteMessage, logs:FilterLogEvents.
EOF
