package local.alba;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.net.Uri;
import android.net.http.SslError;
import android.os.Build;
import android.os.Bundle;
import android.print.PrintManager;
import android.util.Base64;
import android.view.View;
import android.view.WindowInsets;
import android.webkit.*;
import android.widget.*;
import java.io.*;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Alba and Tramonto run inside the app; explicitly selected external links use their own apps. */
public final class MainActivity extends Activity {
 private static final int PICK_IMAGE=10, SAVE_FILE=11, MAX_DOWNLOAD=32*1024*1024;
 private SharedPreferences preferences;
 private WebView web;
 private ProgressBar progress;
 private TextView connection;
 private ValueCallback<Uri[]> fileChooser;
 private byte[] pendingDownload;
 private Runnable nextNavigation;
 private final ExecutorService io=Executors.newSingleThreadExecutor();

 @Override public void onCreate(Bundle state){
  super.onCreate(state);preferences=getSharedPreferences("alba",MODE_PRIVATE);
  LinearLayout root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setBackgroundColor(Color.rgb(245,243,232));
  root.setOnApplyWindowInsetsListener((v,insets)->{
   if(Build.VERSION.SDK_INT>=30){android.graphics.Insets bars=insets.getInsets(WindowInsets.Type.systemBars()|WindowInsets.Type.ime());v.setPadding(bars.left,bars.top,bars.right,bars.bottom);}
   else v.setPadding(insets.getSystemWindowInsetLeft(),insets.getSystemWindowInsetTop(),insets.getSystemWindowInsetRight(),insets.getSystemWindowInsetBottom());return insets;
  });
  LinearLayout nav=new LinearLayout(this);nav.setPadding(dp(8),0,dp(8),0);
  add(nav,"☀ Alba",()->navigate("/"));add(nav,"◒ Tramonto",()->navigate("/tramonto"));add(nav,"⋯",this::menu);root.addView(nav,new LinearLayout.LayoutParams(-1,dp(48)));
  progress=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);root.addView(progress,new LinearLayout.LayoutParams(-1,dp(3)));
  connection=new TextView(this);connection.setTextColor(Color.rgb(112,59,31));connection.setPadding(dp(16),dp(8),dp(16),dp(8));connection.setVisibility(View.GONE);connection.setOnClickListener(v->web.reload());root.addView(connection);
  web=new WebView(this);web.setBackgroundColor(Color.rgb(244,245,238));root.addView(web,new LinearLayout.LayoutParams(-1,0,1));
  WebSettings settings=web.getSettings();settings.setJavaScriptEnabled(true);settings.setDomStorageEnabled(true);settings.setAllowFileAccess(false);settings.setAllowContentAccess(false);settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);settings.setSupportMultipleWindows(false);settings.setUseWideViewPort(true);settings.setBuiltInZoomControls(true);settings.setDisplayZoomControls(false);settings.setUserAgentString(settings.getUserAgentString()+" AlbaAndroid/1.1.0");
  CookieManager.getInstance().setAcceptCookie(true);CookieManager.getInstance().setAcceptThirdPartyCookies(web,false);web.addJavascriptInterface(new NativeActions(),"AlbaNative");
  web.setWebViewClient(new WebViewClient(){
   @Override public boolean shouldOverrideUrlLoading(WebView view,WebResourceRequest request){return handleLink(request.getUrl(),request.isForMainFrame());}
   @Override public boolean shouldOverrideUrlLoading(WebView view,String url){return handleLink(Uri.parse(url),true);}
   @Override public WebResourceResponse shouldInterceptRequest(WebView view,WebResourceRequest request){Uri uri=request.getUrl();String scheme=uri.getScheme();if(("https".equals(scheme)||"http".equals(scheme))&&!sameServer(uri))return new WebResourceResponse("text/plain","UTF-8",403,"Forbidden",java.util.Collections.emptyMap(),new ByteArrayInputStream(new byte[0]));return null;}
   @Override public void onPageStarted(WebView view,String url,android.graphics.Bitmap icon){connection.setVisibility(View.GONE);progress.setVisibility(View.VISIBLE);}
   @Override public void onPageFinished(WebView view,String url){
    CookieManager.getInstance().flush();progress.setVisibility(View.GONE);if(!sameServer(Uri.parse(url)))return;
    view.evaluateJavascript("(()=>{window.print=()=>AlbaNative.printPage();if(window.__albaDownloads)return;window.__albaDownloads=true;document.addEventListener('click',async e=>{const a=e.target.closest('a');if(!a||!a.download||!a.href.startsWith('blob:'))return;e.preventDefault();try{const r=await fetch(a.href),b=await r.blob();if(b.size>33554432)throw Error('Esportazione troppo grande (massimo 32 MB)');const f=new FileReader();f.onload=()=>AlbaNative.saveFile(a.download,b.type||'application/octet-stream',f.result.split(',')[1]);f.readAsDataURL(b);}catch(x){alert(x.message);}},true);})()",null);
   }
   @Override public void onReceivedError(WebView view,WebResourceRequest request,WebResourceError error){if(request.isForMainFrame())showConnection("Server non raggiungibile. Controlla la connessione e tocca qui per riprovare.");}
   @Override public void onReceivedSslError(WebView view,SslErrorHandler handler,SslError error){handler.cancel();showConnection("Certificato HTTPS non valido. Controlla l’indirizzo del server.");}
   @Override public void onReceivedHttpError(WebView view,WebResourceRequest request,WebResourceResponse response){if(request.isForMainFrame()&&response.getStatusCode()>=500)showConnection("Il server non è disponibile. Tocca qui per riprovare.");}
  });
  web.setWebChromeClient(new WebChromeClient(){
   @Override public void onProgressChanged(WebView view,int value){progress.setProgress(value);}
   @Override public boolean onJsAlert(WebView view,String url,String message,JsResult result){new AlertDialog.Builder(MainActivity.this).setMessage(message).setPositiveButton("OK",(d,w)->result.confirm()).setOnCancelListener(d->result.cancel()).show();return true;}
   @Override public boolean onJsConfirm(WebView view,String url,String message,JsResult result){new AlertDialog.Builder(MainActivity.this).setMessage(message).setNegativeButton("Annulla",(d,w)->result.cancel()).setPositiveButton("Conferma",(d,w)->result.confirm()).setOnCancelListener(d->result.cancel()).show();return true;}
   @Override public boolean onJsPrompt(WebView view,String url,String message,String defaultValue,JsPromptResult result){EditText input=new EditText(MainActivity.this);input.setText(defaultValue);new AlertDialog.Builder(MainActivity.this).setMessage(message).setView(input).setNegativeButton("Annulla",(d,w)->result.cancel()).setPositiveButton("Salva",(d,w)->result.confirm(input.getText().toString())).setOnCancelListener(d->result.cancel()).show();return true;}
   @Override public boolean onJsBeforeUnload(WebView view,String url,String message,JsResult result){new AlertDialog.Builder(MainActivity.this).setMessage("Ci sono modifiche non salvate. Vuoi lasciare la pagina?").setNegativeButton("Resta",(d,w)->result.cancel()).setPositiveButton("Esci",(d,w)->result.confirm()).setOnCancelListener(d->result.cancel()).show();return true;}
   @Override public boolean onShowFileChooser(WebView view,ValueCallback<Uri[]> callback,FileChooserParams params){if(fileChooser!=null)fileChooser.onReceiveValue(null);fileChooser=callback;Intent intent=new Intent(Intent.ACTION_OPEN_DOCUMENT);intent.addCategory(Intent.CATEGORY_OPENABLE);intent.setType("image/*");intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE,params.getMode()==FileChooserParams.MODE_OPEN_MULTIPLE);try{startActivityForResult(intent,PICK_IMAGE);}catch(Exception error){fileChooser.onReceiveValue(null);fileChooser=null;toast("Nessun selettore immagini disponibile.");}return true;}
  });
  web.setDownloadListener((url,agent,disposition,mime,length)->downloadUrl(url,agent,disposition,mime));setContentView(root);root.requestApplyInsets();
  if(state==null||web.restoreState(state)==null)web.loadUrl(base()+"/");
  if(Build.VERSION.SDK_INT>=33)getOnBackInvokedDispatcher().registerOnBackInvokedCallback(android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT,()->back());
 }
 private int dp(int value){return Math.round(value*getResources().getDisplayMetrics().density);}
 private void add(LinearLayout root,String text,Runnable action){Button b=new Button(this);b.setText(text);b.setTextSize(13);b.setAllCaps(false);b.setOnClickListener(v->action.run());root.addView(b,new LinearLayout.LayoutParams(0,-1,1));}
 private String base(){return preferences.getString("server",getString(R.string.default_server));}
 private boolean sameServer(Uri uri){Uri origin=Uri.parse(base());return "https".equals(uri.getScheme())&&origin.getHost()!=null&&origin.getHost().equalsIgnoreCase(uri.getHost())&&origin.getPort()==uri.getPort()&&uri.getUserInfo()==null;}
 private boolean handleLink(Uri uri,boolean main){
  if(sameServer(uri)){String path=uri.getPath();if(path!=null&&(path.startsWith("/auth/google")||path.startsWith("/auth/github")||path.startsWith("/auth/discord"))){toast("Nell’app accedi con password, chiave personale o SMS.");return true;}return false;}
  if(main&&("https".equals(uri.getScheme())||"mailto".equals(uri.getScheme())||"tel".equals(uri.getScheme())))try{startActivity(new Intent(Intent.ACTION_VIEW,uri));}catch(Exception error){toast("Non è disponibile un’app per questo collegamento.");}return true;
 }
 private void afterSave(Runnable action){if(nextNavigation!=null)return;nextNavigation=action;web.evaluateJavascript("(async()=>typeof TramontoTools==='undefined'||await TramontoTools.saveDoc())().then(ok=>AlbaNative.navigationReady(ok)).catch(()=>AlbaNative.navigationReady(false))",null);}
 private void navigate(String path){afterSave(()->web.loadUrl(base()+path));}
 private void back(){afterSave(()->{if(web.canGoBack())web.goBack();else finish();});}
 @Override public void onBackPressed(){back();}
 private void menu(){new AlertDialog.Builder(this).setTitle("Alba · Tramonto").setItems(new String[]{"Ricarica","Stampa / salva PDF","Cambia server HTTPS"},(d,w)->{if(w==0)afterSave(()->web.reload());else if(w==1)printPage();else afterSave(this::configure);}).show();}
 private void configure(){
  EditText input=new EditText(this);input.setSingleLine();input.setInputType(android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_VARIATION_URI);input.setText(base());
  AlertDialog dialog=new AlertDialog.Builder(this).setTitle("Il tuo server Alba").setView(input).setNegativeButton("Annulla",null).setPositiveButton("Salva",null).create();
  dialog.setOnShowListener(d->dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v->{String value=input.getText().toString().trim().replaceAll("/+$","");Uri uri=Uri.parse(value);
   if("https".equals(uri.getScheme())&&uri.getHost()!=null&&uri.getUserInfo()==null&&uri.getQuery()==null&&uri.getFragment()==null&&(uri.getPath()==null||uri.getPath().isEmpty())){preferences.edit().putString("server",value).apply();web.clearHistory();web.loadUrl(value+"/");dialog.dismiss();}else input.setError("Inserisci un’origine HTTPS senza percorso o credenziali.");}));dialog.show();
 }
 private void showConnection(String message){connection.setText(message);connection.setVisibility(View.VISIBLE);progress.setVisibility(View.GONE);}
 private void toast(String message){Toast.makeText(this,message,Toast.LENGTH_LONG).show();}
 private void printPage(){if(sameServer(Uri.parse(web.getUrl()==null?"":web.getUrl())))((PrintManager)getSystemService(PRINT_SERVICE)).print("Tramonto",web.createPrintDocumentAdapter("Tramonto"),null);}
 public final class NativeActions {
  @JavascriptInterface public void printPage(){runOnUiThread(()->MainActivity.this.printPage());}
  @JavascriptInterface public void navigationReady(boolean ok){runOnUiThread(()->{Runnable action=nextNavigation;nextNavigation=null;if(ok&&action!=null)action.run();else if(!ok)toast("Modifiche non salvate. Esportale prima di uscire.");});}
  @JavascriptInterface public void saveFile(String name,String mime,String data){if(data==null||data.length()>MAX_DOWNLOAD*4/3+8){runOnUiThread(()->toast("Esportazione troppo grande (massimo 32 MB)."));return;}try{byte[] bytes=Base64.decode(data,Base64.DEFAULT);runOnUiThread(()->chooseDestination(name,mime,bytes));}catch(Exception error){runOnUiThread(()->toast("Esportazione non valida."));}}
 }
 private void chooseDestination(String name,String mime,byte[] bytes){
  if(pendingDownload!=null){toast("Completa prima il salvataggio precedente.");return;}pendingDownload=bytes;
  String filename=(name==null||name.isEmpty()?"Tramonto":name).replaceAll("[/\\\\\\p{Cntrl}]","_");filename=filename.substring(0,Math.min(filename.length(),180));
  Intent intent=new Intent(Intent.ACTION_CREATE_DOCUMENT);intent.addCategory(Intent.CATEGORY_OPENABLE);intent.setType(mime!=null&&mime.matches("[\\w.+-]+/[\\w.+-]+")?mime:"application/octet-stream");intent.putExtra(Intent.EXTRA_TITLE,filename);
  try{startActivityForResult(intent,SAVE_FILE);}catch(Exception error){pendingDownload=null;toast("Nessun selettore documenti disponibile.");}
 }
 private void downloadUrl(String url,String agent,String disposition,String mime){
  if(!sameServer(Uri.parse(url))){toast("Scarica i file dal tuo server HTTPS.");return;}String cookies=CookieManager.getInstance().getCookie(url);String filename=URLUtil.guessFileName(url,disposition,mime);toast("Preparazione del file…");
  io.execute(()->{HttpURLConnection request=null;try{request=(HttpURLConnection)new URL(url).openConnection();request.setInstanceFollowRedirects(false);request.setConnectTimeout(15000);request.setReadTimeout(30000);request.setRequestProperty("User-Agent",agent);if(cookies!=null)request.setRequestProperty("Cookie",cookies);if(request.getResponseCode()!=200)throw new IOException();
   ByteArrayOutputStream bytes=new ByteArrayOutputStream();try(InputStream stream=request.getInputStream()){byte[] buffer=new byte[8192];int count;while((count=stream.read(buffer))!=-1){if(bytes.size()+count>MAX_DOWNLOAD)throw new IOException();bytes.write(buffer,0,count);}}byte[] result=bytes.toByteArray();runOnUiThread(()->chooseDestination(filename,mime,result));
  }catch(Exception error){runOnUiThread(()->toast("Download non riuscito. Controlla accesso, connessione e dimensione (massimo 32 MB)."));}finally{if(request!=null)request.disconnect();}});
 }
 @Override protected void onActivityResult(int request,int result,Intent data){super.onActivityResult(request,result,data);
  if(request==PICK_IMAGE&&fileChooser!=null){Uri[] selected=null;if(result==RESULT_OK&&data!=null){if(data.getClipData()!=null){selected=new Uri[data.getClipData().getItemCount()];for(int i=0;i<selected.length;i++)selected[i]=data.getClipData().getItemAt(i).getUri();}else if(data.getData()!=null)selected=new Uri[]{data.getData()};}fileChooser.onReceiveValue(selected);fileChooser=null;}
  if(request==SAVE_FILE){byte[] bytes=pendingDownload;pendingDownload=null;if(result==RESULT_OK&&data!=null&&data.getData()!=null&&bytes!=null){Uri uri=data.getData();io.execute(()->{try(OutputStream stream=getContentResolver().openOutputStream(uri)){if(stream==null)throw new IOException();stream.write(bytes);runOnUiThread(()->toast("File salvato."));}catch(Exception error){runOnUiThread(()->toast("Impossibile salvare il file."));}});}}
 }
 @Override protected void onSaveInstanceState(Bundle state){super.onSaveInstanceState(state);web.saveState(state);}
 @Override protected void onPause(){super.onPause();CookieManager.getInstance().flush();}
 @Override protected void onDestroy(){if(fileChooser!=null)fileChooser.onReceiveValue(null);web.removeJavascriptInterface("AlbaNative");web.destroy();io.shutdown();super.onDestroy();}
}
