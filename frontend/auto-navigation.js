// Only a fresh upload in this page session may trigger automatic navigation.
// A restored project or a return to the photo screen must remain there.
let activeUpload = null;
let storageFailure = null;
const validId = id => /^[a-f0-9]{32}$/.test(id || '');
const key = id => `embedded-vision:auto-open:${id}`;
export function sessionStore(){try{return window.sessionStorage;}catch{return null;}}
export function markAutoLaunch(id,storage=sessionStore()){
 activeUpload=null;storageFailure=null;
 if(!validId(id))return false;
 if(!storage){storageFailure=id;return false;}
 try{storage.setItem(key(id),'pending');if(storage.getItem(key(id))!=='pending'){storageFailure=id;return false;}activeUpload=id;return true;}catch{storageFailure=id;return false;}
}
export function cancelAutoLaunch(storage=sessionStore()){
 if(activeUpload&&storage)try{storage.removeItem(key(activeUpload));}catch{}
 activeUpload=null;
}
export function consumeAutoLaunch(id,storage=sessionStore()){
 if(!validId(id)||activeUpload!==id||!storage)return false;
 try{if(storage.getItem(key(id))!=='pending')return false;storage.removeItem(key(id));activeUpload=null;return true;}catch{activeUpload=null;return false;}
}

export function autoLaunchStorageFailed(id){return storageFailure===id;}
