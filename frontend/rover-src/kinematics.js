// Differential-drive kinematics, not a motor/firmware/electrical simulator.
export const ROVER_ASSUMPTIONS = Object.freeze({trackWidthM:0.14,maxWheelSpeedMps:0.20,durationSeconds:1});
export const ROVER_COMMANDS = Object.freeze({
 forward:[0.5,0.5],backward:[-0.5,-0.5],left:[0,0.5],right:[0.5,0],stop:[0,0]
});

// Local +X is the nose, +Y is up and -Z is the vehicle's left.
// The 2D model's positive Y and heading mean left, so its Y is negated
// when mapped into the Three.js ground plane.
export const ROVER_WHEEL_LAYOUT=Object.freeze([
 Object.freeze({side:'left',z:-.07}),Object.freeze({side:'right',z:.07})
]);
export function roverPoseToWorld(pose){return {x:pose.x,z:-pose.y,rotationY:pose.heading};}

export function stepRover(state,left,right,seconds,assumptions=ROVER_ASSUMPTIONS) {
 const v=[state.x,state.y,state.heading,left,right,seconds,assumptions.trackWidthM,assumptions.maxWheelSpeedMps];
 if(!v.every(Number.isFinite)||Math.abs(left)>1||Math.abs(right)>1||seconds<0||seconds>2||assumptions.trackWidthM<=0||assumptions.maxWheelSpeedMps<=0)throw new RangeError('invalid rover state');
 const vl=left*assumptions.maxWheelSpeedMps,vr=right*assumptions.maxWheelSpeedMps;
 const speed=(vl+vr)/2, omega=(vr-vl)/assumptions.trackWidthM, next=state.heading+omega*seconds;
 const x=state.x+(Math.abs(omega)<1e-12?speed*seconds*Math.cos(state.heading):speed/omega*(Math.sin(next)-Math.sin(state.heading)));
 const y=state.y+(Math.abs(omega)<1e-12?speed*seconds*Math.sin(state.heading):speed/omega*(Math.cos(state.heading)-Math.cos(next)));
 return {x,y,heading:next};
}
