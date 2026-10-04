package local.alba;
import android.app.Instrumentation;
import android.content.Intent;
import android.os.Bundle;
import android.view.View;
import android.view.ViewGroup;
import android.widget.*;
import org.json.*;
import java.lang.reflect.*;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;

/** UI fixtures only. No real credentials, Telegram messages or model claims. */
public final class NativeUiSmoke extends Instrumentation {
    private MainActivity activity;
    private JSONObject fixtures;
    private FakeApi fake;
    private Throwable failure;
    private int checks=0;
    public void onCreate(Bundle arguments){super.onCreate(arguments);start();}
    public void onStart(){new Thread(()->{
        Bundle result=new Bundle();try{
            byte[] data=new byte[65536];int count;StringBuilder json=new StringBuilder();try(java.io.InputStream in=getContext().getAssets().open("fixture.json")){while((count=in.read(data))!=-1)json.append(new String(data,0,count,"UTF-8"));}fixtures=new JSONObject(json.toString());
            activity=(MainActivity)startActivitySync(new Intent(Intent.ACTION_MAIN).setClassName("local.alba","local.alba.MainActivity").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            ((ExecutorService)field("io")).submit(()->{}).get(35,TimeUnit.SECONDS);waitForIdleSync();
            fake=new FakeApi();ui(()->{set("api",fake);set("english",true);call("signedIn",new Class[]{JSONObject.class},new JSONObject().put("name","Smoke").put("user_id",1).put("is_admin",true));});settle();
            ui(()->{assertNative(activity.getWindow().getDecorView());check(visible("A native answer."),"Native markdown answer");check(hasClass(activity.getWindow().getDecorView(),TableLayout.class),"Native markdown table");((EditText)field("composer")).setText("Unsent draft");call("navigate",new Class[]{int.class},4);});settle();
            ui(()->{check(visible("Verified function."),"Topic diary");call("navigate",new Class[]{int.class},0);});settle();
            ui(()->{check(((EditText)field("composer")).getText().toString().equals("Unsent draft"),"Chat draft survives menu");call("navigate",new Class[]{int.class},6);});settle();
            ui(()->{check(visible("Personal Qwen · CPU training"),"Native model panel");call("navigate",new Class[]{int.class},8);});settle();
            ui(()->{check(visible("Raspberry Pi"),"Native system panel");call("navigate",new Class[]{int.class},5);});settle();
            ui(()->{check(visible("#1 · chat · assistant"),"All activity panel");call("navigate",new Class[]{int.class},2);call("openNote",new Class[]{int.class},1);});settle();
            ui(()->{((EditText)field("noteText")).append(" Edited.");JSONObject saved=(JSONObject)call("noteData",new Class[]{});JSONObject original=fixtures.getJSONObject("note").getJSONObject("content"),content=saved.getJSONObject("content");check(content.getJSONObject("graph").toString().equals(original.getJSONObject("graph").toString()),"Graph survives native text editing");check(content.getJSONArray("formulas").toString().equals(original.getJSONArray("formulas").toString()),"Formula survives native text editing");check(content.getJSONObject("network").toString().equals(original.getJSONObject("network").toString()),"Network survives native text editing");call("saveNote",new Class[]{});});settle();
            ui(()->{check(!((Boolean)field("noteChanged")),"Native save clears dirty state");check(fake.saved!=null&&fake.saved.optInt("version")==1,"Optimistic version is sent");set("english",false);call("navigate",new Class[]{int.class},9);check(visible("Lingua dell’app"),"Italian UI");set("note",null);set("noteChanged",false);call("navigate",new Class[]{int.class},0);call("menu",new Class[]{});});waitForIdleSync();
            ui(()->check(((String[])call("sections",new Class[]{}))[4].equals("Diario di apprendimento"),"Dropdown section names"));
            ui(()->{call("navigate",new Class[]{int.class},0);((EditText)field("composer")).setText("Notte draft");Intent link=new Intent(Intent.ACTION_VIEW,android.net.Uri.parse("https://fixture.invalid/"));call("onNewIntent",new Class[]{Intent.class},link);check(link.getData()==null,"Warm link URI cleared");check(((Integer)field("section"))==1,"Warm link switches native section");check(((EditText)field("composer")).getText().toString().isEmpty(),"Warm link does not copy another channel draft");call("navigate",new Class[]{int.class},0);check(((EditText)field("composer")).getText().toString().equals("Notte draft"),"Warm link preserves source draft");Intent bad=new Intent(Intent.ACTION_VIEW,android.net.Uri.parse("https://evil.invalid/notte#web_key=secret"));call("intent",new Class[]{Intent.class},bad);check(bad.getData()==null&&((String)field("pendingKey")).isEmpty(),"External server key rejected and cleared");call("persistDrafts",new Class[]{});call("signedIn",new Class[]{JSONObject.class},new JSONObject().put("user_id",2).put("is_admin",true));check(((String[])field("drafts"))[0].isEmpty(),"Account switch clears private drafts");});settle();
            if(failure!=null)throw new RuntimeException(failure);
            result.putString("stream","PASS: "+checks+" native UI checks; fixture API; no browser views\n");finish(-1,result);
        }catch(Throwable error){java.io.StringWriter trace=new java.io.StringWriter();error.printStackTrace(new java.io.PrintWriter(trace));result.putString("stream","FAIL after "+checks+" checks: "+trace+"\n");finish(0,result);}
    },"native-smoke").start();}
    private void settle() throws Exception {((ExecutorService)field("io")).submit(()->{}).get(10,TimeUnit.SECONDS);waitForIdleSync();Thread.sleep(150);waitForIdleSync();if(failure!=null)throw new RuntimeException(failure);}
    private interface Task {void run() throws Exception;}
    private void ui(Task task){runOnMainSync(()->{try{task.run();}catch(Throwable e){failure=e;}});}
    private Object field(String name) throws Exception {Field field=MainActivity.class.getDeclaredField(name);field.setAccessible(true);return field.get(activity);}
    private void set(String name,Object value) throws Exception {Field field=MainActivity.class.getDeclaredField(name);field.setAccessible(true);field.set(activity,value);}
    private Object call(String name,Class[] types,Object... args) throws Exception {Method method=MainActivity.class.getDeclaredMethod(name,types);method.setAccessible(true);return method.invoke(activity,args);}
    private void check(boolean value,String label){checks++;if(!value)throw new AssertionError(label);}
    private boolean visible(String text){return contains(activity.getWindow().getDecorView(),text);}
    private boolean contains(View view,String text){if(view instanceof TextView&&((TextView)view).getText().toString().contains(text))return true;if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++)if(contains(((ViewGroup)view).getChildAt(i),text))return true;return false;}
    private boolean hasClass(View view,Class type){if(type.isInstance(view))return true;if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++)if(hasClass(((ViewGroup)view).getChildAt(i),type))return true;return false;}
    private void assertNative(View view){check(!view.getClass().getName().startsWith("android.webkit."),"No browser views");if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++)assertNative(((ViewGroup)view).getChildAt(i));}
    private final class FakeApi extends NativeApi {
        JSONObject saved;
        FakeApi() throws Exception {super(getTargetContext(),"https://fixture.invalid");}
        @Override synchronized JSONObject request(String method,String path,JSONObject body) throws Exception {
            if(path.equals("/api/notte/status"))return fixtures.getJSONObject("status");
            if(path.startsWith("/api/notte/events"))return fixtures.getJSONObject("events");
            if(path.equals("/api/notte/diary"))return fixtures.getJSONObject("diary");
            if(path.equals("/api/tramonto/notebooks"))return new JSONObject("{\"notebooks\":[]}");
            if(path.equals("/api/tramonto/notes/1")){if(method.equals("PUT")){saved=body;return new JSONObject("{\"version\":2}");}return new JSONObject(fixtures.getJSONObject("note").toString());}
            return new JSONObject("{\"ok\":true}");
        }
    }
}
