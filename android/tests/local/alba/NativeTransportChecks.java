package local.alba;
import android.content.Context;
import org.json.JSONObject;
import java.net.*;
import java.io.*;
import java.util.*;
import java.util.concurrent.*;

/** Exercise the actual transport's credential and concurrency code with controlled HTTPS connections. */
final class NativeTransportChecks {
    private static final CountDownLatch entered=new CountDownLatch(1),release=new CountDownLatch(1);
    private static final Map<String,Connection> receipts=new ConcurrentHashMap<>();
    static int run(Context context) throws Exception {
        URL.setURLStreamHandlerFactory(protocol->protocol.equals("https")?new URLStreamHandler(){protected URLConnection openConnection(URL url){Connection connection=new Connection(url);receipts.put(url.getPath(),connection);return connection;}}:null);
        NativeApi api=new NativeApi(context,"https://transport.fixture.invalid");ExecutorService workers=Executors.newFixedThreadPool(2);int checks=0;
        try {
            api.clear();api.request("POST","/api/login",new JSONObject());api.request("POST","/api/action",new JSONObject().put("action","fixture"));
            check("session=fixture-session".equals(receipts.get("/api/action").getRequestProperty("Cookie")),"Login cookie propagated");checks++;
            check("fixture-csrf".equals(receipts.get("/api/action").getRequestProperty("X-CSRF-Token")),"CSRF propagated atomically with login cookie");checks++;
            Future<JSONObject> slow=workers.submit(()->api.request("GET","/api/slow",null));check(entered.await(2,TimeUnit.SECONDS),"Slow request started");checks++;
            Future<JSONObject> quick=workers.submit(()->api.request("GET","/api/quick",null));check(quick.get(2,TimeUnit.SECONDS).optBoolean("ok"),"Other API requests are not blocked by slow polling");checks++;
            api.clear();release.countDown();slow.get(2,TimeUnit.SECONDS);api.request("POST","/api/after-clear",new JSONObject());
            check(receipts.get("/api/after-clear").getRequestProperty("Cookie")==null,"Late responses cannot resurrect a cleared session");checks++;
            check("".equals(receipts.get("/api/after-clear").getRequestProperty("X-CSRF-Token")),"Late responses cannot restore old CSRF");checks++;
            try{api.request("GET","/api/expired",null);throw new AssertionError("Expired session accepted");}catch(NativeApi.Failure error){check(error.status==401,"Server auth_expired is interpreted as a login requirement");checks++;}
            check(api.request("GET","/api/tramonto/fonts",null).optString("padding").length()>2*1024*1024,"Large valid font collections accepted");checks++;
            try{api.request("GET","/api/history",null);throw new AssertionError("Unbounded history accepted");}catch(Exception error){check("Response exceeds limit".equals(error.getMessage()),"Other endpoints keep their bounded response size");checks++;}
            return checks;
        }finally{release.countDown();workers.shutdownNow();api.clear();}
    }
    private static void check(boolean value,String message){if(!value)throw new AssertionError(message);}
    private static final class Connection extends HttpURLConnection {
        Connection(URL url){super(url);}
        public void connect(){}public void disconnect(){}public boolean usingProxy(){return false;}
        public OutputStream getOutputStream(){return new ByteArrayOutputStream();}
        public int getResponseCode() throws IOException {if(url.getPath().equals("/api/slow")){entered.countDown();try{if(!release.await(5,TimeUnit.SECONDS))throw new IOException("Fixture timeout");}catch(InterruptedException error){throw new IOException(error);}}return url.getPath().equals("/api/expired")?403:200;}
        public Map<String,List<String>> getHeaderFields(){if(url.getPath().equals("/api/login"))return Collections.singletonMap("Set-Cookie",Collections.singletonList("session=fixture-session; Secure; HttpOnly"));if(url.getPath().equals("/api/slow"))return Collections.singletonMap("Set-Cookie",Collections.singletonList("session=old-session; Secure; HttpOnly"));return Collections.emptyMap();}
        public InputStream getInputStream() throws IOException {String path=url.getPath(),body="{\"ok\":true}";if(path.equals("/api/login"))body="{\"csrf\":\"fixture-csrf\"}";if(path.equals("/api/slow"))body="{\"csrf\":\"old-csrf\"}";if(path.equals("/api/tramonto/fonts")||path.equals("/api/history")){char[] chars=new char[2*1024*1024+100];Arrays.fill(chars,'x');body="{\"padding\":\""+new String(chars)+"\"}";}return new ByteArrayInputStream(body.getBytes("UTF-8"));}
        public InputStream getErrorStream(){return new ByteArrayInputStream("{\"error\":\"expired\",\"code\":\"auth_expired\"}".getBytes());}
    }
}
