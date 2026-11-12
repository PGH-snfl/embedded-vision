// Prototype state machine; timestamps in milliseconds, distances in centimetres.
// Its wheel commands approximate the Arduino sketch, but do not execute it.
export function createObstacleController({nearCm=20, backMs=400, turnMs=600}={}) {
 let mode='forward', started=0;
 function reset(){mode='forward';started=0;}
 function step(distance,now){
  if(!Number.isFinite(now))throw new TypeError('invalid timestamp');
  if(distance===null||!Number.isFinite(distance)||distance<0){reset();return 'stop';}
  if(mode==='forward'&&distance<=nearCm){mode='backward';started=now;}
  if(mode==='backward'&&now-started>=backMs){mode='left';started=now;}
  if(mode==='left'&&now-started>=turnMs)mode='forward';
  return mode;
 }
 return {step,reset};
}
