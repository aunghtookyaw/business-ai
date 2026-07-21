/* Secure UUID v4 generation for localhost, LAN HTTP, and older browsers. */
((root)=>{
  const formatV4=bytes=>{
    bytes[6]=(bytes[6]&15)|64;
    bytes[8]=(bytes[8]&63)|128;
    const hex=Array.from(bytes,value=>value.toString(16).padStart(2,'0'));
    return `${hex.slice(0,4).join('')}-${hex.slice(4,6).join('')}-${hex.slice(6,8).join('')}-${hex.slice(8,10).join('')}-${hex.slice(10,16).join('')}`;
  };
  async function secureUuidV4(){
    const webCrypto=root.crypto;
    if(webCrypto&&typeof webCrypto.randomUUID==='function')return webCrypto.randomUUID();
    if(webCrypto&&typeof webCrypto.getRandomValues==='function')return formatV4(webCrypto.getRandomValues(new Uint8Array(16)));
    const response=await root.fetch('/business-os/api/security/idempotency-token',{method:'POST',headers:{'X-Business-OS-Request':'uuid-v1'}});
    const text=await response.text();
    let body;
    try{body=JSON.parse(text)}catch(_error){throw new Error(`Secure idempotency endpoint returned an invalid response (${response.status})`)}
    if(!response.ok||!body.ok||!body.token)throw new Error(body.error||'Secure idempotency token is unavailable');
    return body.token;
  }
  root.BusinessOS=root.BusinessOS||{};
  root.BusinessOS.secureUuidV4=secureUuidV4;
})(globalThis);
