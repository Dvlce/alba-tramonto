package local.alba;

import android.content.Context;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URI;
import java.net.URL;
import java.util.List;
import java.util.Map;

/** Same-origin JSON transport. No browser, Javascript or redirect following. */
class NativeApi {
    final String origin;
    private final SessionStore sessions;
    private String cookie,csrf="";
    static class Failure extends Exception {
        final int status;
        Failure(int status,String message){super(message);this.status=status;}
    }
    NativeApi(Context context,String origin) throws Exception {
        URI uri=new URI(origin);
        if(!"https".equals(uri.getScheme())||uri.getHost()==null||uri.getUserInfo()!=null||uri.getQuery()!=null||uri.getFragment()!=null||!(uri.getPath().isEmpty()||"/".equals(uri.getPath())))throw new Exception("Use an HTTPS server origin");
        this.origin=origin.replaceAll("/$","");sessions=new SessionStore(context);cookie=sessions.load();
    }
    synchronized JSONObject request(String method,String path,JSONObject body) throws Exception {
        if(!path.startsWith("/api/")||path.startsWith("//")||path.contains("\\")||path.contains("\r")||path.contains("\n"))throw new Exception("Invalid API path");
        HttpURLConnection connection=(HttpURLConnection)new URL(origin+path).openConnection();
        try{
            connection.setInstanceFollowRedirects(false);connection.setConnectTimeout(15000);connection.setReadTimeout(30000);
            connection.setRequestMethod(method);connection.setRequestProperty("Accept","application/json");
            connection.setRequestProperty("User-Agent","Alba-Native-Android/1.4");connection.setRequestProperty("Origin",origin);
            if(!cookie.isEmpty())connection.setRequestProperty("Cookie","session="+cookie);
            if(!"GET".equals(method)){
                connection.setRequestProperty("X-CSRF-Token",csrf);connection.setRequestProperty("Content-Type","application/json");
                connection.setDoOutput(true);byte[] bytes=(body==null?"{}":body.toString()).getBytes("UTF-8");
                connection.setFixedLengthStreamingMode(bytes.length);connection.getOutputStream().write(bytes);connection.getOutputStream().close();
            }
            int status=connection.getResponseCode();InputStream input=status>=400?connection.getErrorStream():connection.getInputStream();
            ByteArrayOutputStream buffer=new ByteArrayOutputStream();
            if(input!=null){try(InputStream stream=input){byte[] bytes=new byte[8192];int count;while((count=stream.read(bytes))!=-1){buffer.write(bytes,0,count);if(buffer.size()>2*1024*1024)throw new Exception("Response exceeds limit");}}}
            JSONObject result;
            try{result=new JSONObject(buffer.toString("UTF-8"));}catch(Exception e){throw new Failure(status,"Server response unavailable (HTTP "+status+")");}
            if(status<200||status>=300)throw new Failure(result.optString("code").equals("auth_expired")?401:status,result.optString("error","HTTP "+status));
            for(Map.Entry<String,List<String>> header:connection.getHeaderFields().entrySet()){
                if(header.getKey()!=null&&header.getKey().equalsIgnoreCase("Set-Cookie"))for(String value:header.getValue()){
                    if(value.startsWith("session=")){cookie=value.substring(8).split(";",2)[0];sessions.save(cookie);}
                }
            }
            if(result.has("csrf"))csrf=result.getString("csrf");
            return result;
        }finally{connection.disconnect();}
    }
    synchronized void clear() throws Exception {cookie="";csrf="";sessions.save("");}
}
