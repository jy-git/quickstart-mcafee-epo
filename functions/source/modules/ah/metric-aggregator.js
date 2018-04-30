var AWS = require('aws-sdk');
var cloudwatch = new AWS.CloudWatch();
//Alarm constants
const apacheBusyAlarm = process.env.APACHE_BUSY_ALARM_NAME
const dbBlockedConnHighAlarm = process.env.DB_BLOCKED_CONN_ALARM_NAME
const  aggregatorAlarm = process.env.AGGREGATOR_ALAM_NAME
var sourceAlarms = {};
sourceAlarms[apacheBusyAlarm] = 'ALARM';
sourceAlarms[dbBlockedConnHighAlarm] = 'OK';var targetAlarms = [aggregatorAlarm];
var soureAlarmsRef = {};
var targetAlarmsRef = {};
exports.handler = function(event, context) {
  console.log("Aggregator: Event Received :\n", JSON.stringify(event));
  var records = event.Records;
  var message = records[0].Sns.Message;
  var alarm = JSON.parse(message);

  if(alarm.NewStateValue != 'ALARM') {
    //Mostly unreachable code...
    console.log('Aggregator: Alarm '+alarm.AlarmName+ ' is in '+alarm.NewStateValue + ', so do nothing');
    return;
  }
  processAlarms(alarm);
};

function processAlarms(alarm) {
  console.log('Aggregator: Alarm '+alarm.AlarmName+ ' is being processed');
  var params = {
    AlarmNames:[apacheBusyAlarm, dbBlockedConnHighAlarm, aggregatorAlarm]
  };
  console.log('Aggregator: Get all Alarms with the prefix' + JSON.stringify(params));
  cloudwatch.describeAlarms(params, (err, data) => {
      if (err) {
        console.log('Aggregator: ERROR: '+err.message);
        return;
      }
      // TODO: Since now we are using Env variables, we have whole name of the Alarm, so the below code
      // can be improved
      try {
        Object.keys(sourceAlarms).forEach(sourceAlarm => {
          data.MetricAlarms.forEach(alarm => {
            if(alarm.AlarmName.includes(sourceAlarm))  {
              console.log(alarm.AlarmName);
              soureAlarmsRef[sourceAlarm] = alarm;
            }
          });
        });
        targetAlarms.forEach(targetAlarm => {
          data.MetricAlarms.forEach(alarm => {
            if(alarm.AlarmName.includes(targetAlarm))  {
              console.log(alarm.AlarmName);
              targetAlarmsRef[targetAlarm] = alarm;
            }
          });
        });

        decideTargetAlarmAction();
      } catch (e) {
        console.log('Aggregator: ERROR: '+e.message);
        return;
      }
  });
}

function decideTargetAlarmAction() {
  console.log('Aggregator: Deciding to trigger ALARM for target alarms or not');
  var sourceAlarmStates = {};
  for(var key in soureAlarmsRef){
      sourceAlarmStates[key] = soureAlarmsRef[key].StateValue;
      if(soureAlarmsRef[key].StateValue != sourceAlarms[key]) {
        console.log(key +' is in '+ soureAlarmsRef[key].StateValue +' state but expected to be in '+sourceAlarms[key]+', so not triggering TargetAlarms');
        return;
      }
  }
  console.log('Aggregator: State of all the Source Alarms are :'+JSON.stringify(sourceAlarmStates));
  console.log('Aggregator: Since all source alarms are in expected state('+JSON.stringify(sourceAlarms)+'), move all target alarms to ALARM state');
  for(var key in targetAlarmsRef){
      triggerAlarmByPuttingMetricData(targetAlarmsRef[key]);
  }
}

function triggerAlarmByPuttingMetricData(alarm) {
  console.log('Aggregator: Triggering '+alarm.AlarmName +' indirectly by sending metric data which will breach the threshold of alarm '+ alarm.AlarmName);
  var params = {
    MetricData: [
      {
        MetricName: alarm.MetricName,
        Dimensions: alarm.Dimensions,
        Timestamp: new Date,
        Value: 1.0
      },
    ],
    Namespace: alarm.Namespace
  };

  cloudwatch.putMetricData(params, function(err, data) {
    if (err) console.log(err, err.stack);
    else     console.log(data);
  });
}
